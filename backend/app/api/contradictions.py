from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.api.concepts import serialize_claim
from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.contradictions import CLASSIFICATIONS, ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.models import Contradiction
from worker.tasks.create_revision import create_revision

logger = logging.getLogger(__name__)

router = APIRouter()


class ClassifyBody(BaseModel):
    classification: str


async def _serialize_contradiction(
    contradiction: Contradiction, claims: ClaimRepository
) -> dict[str, Any] | None:
    claim_a = await claims.get(contradiction.claim_a_id)
    claim_b = await claims.get(contradiction.claim_b_id)
    if claim_a is None or claim_b is None:
        return None
    return {
        "id": str(contradiction.id),
        "concept_id": str(contradiction.concept_id),
        "claim_a": serialize_claim(claim_a),
        "claim_b": serialize_claim(claim_b),
        "similarity": contradiction.similarity,
        "classification": contradiction.classification,
        "rationale": contradiction.rationale,
        "created_at": contradiction.created_at.isoformat(),
        "classified_at": contradiction.classified_at.isoformat()
        if contradiction.classified_at
        else None,
    }


async def maybe_enqueue_revision_synthesis(
    user_id: str, contradiction_id: str, classification: str
) -> None:
    """Auto-enqueue revision synthesis when a contradiction is classified
    'evolution'. Must be called AFTER the classify transaction commits, never
    from inside the same session() block that performed the classify —
    sending the dramatiq message before commit risks create_revision reading
    a contradiction row that isn't visible yet under READ COMMITTED
    isolation (the bug Phase 2 Plan 2's auto-enqueue wiring already fixed
    once). Called from both this module's classify endpoint and the
    Custodian Logging accept endpoint, so both classify paths behave
    identically."""
    if classification != "evolution":
        return
    try:
        async with session(user_id) as conn:
            revision_job = await JobRepository(conn).create(
                user_id, "create_revision", payload={"contradiction_id": contradiction_id}
            )
        create_revision.send(contradiction_id, user_id, str(revision_job.id))
    except Exception as exc:
        logger.warning(
            "failed to auto-enqueue create_revision for contradiction %s: %s",
            contradiction_id,
            exc,
        )


@router.get("/contradictions")
async def list_contradictions(
    concept_id: str | None = None,
    classification: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        contradictions = await ContradictionRepository(conn).list(
            concept_id=concept_id,
            classification=classification,
            limit=limit,
            offset=offset,
        )
        claims = ClaimRepository(conn)
        result = []
        for contradiction in contradictions:
            serialized = await _serialize_contradiction(contradiction, claims)
            if serialized is not None:
                result.append(serialized)
        return result


@router.get("/contradictions/count")
async def count_contradictions(
    concept_id: str | None = None,
    classification: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ContradictionRepository(conn).count(
            concept_id=concept_id, classification=classification
        )
    return {"total": total}


@router.post("/contradictions/{contradiction_id}/classify")
async def classify_contradiction(
    contradiction_id: str,
    body: ClassifyBody,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.classification not in CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"classification must be one of {sorted(CLASSIFICATIONS)}",
        )
    async with session(user_id) as conn:
        contradiction = await ContradictionRepository(conn).classify(
            contradiction_id, body.classification
        )
        if contradiction is None:
            raise HTTPException(status_code=404, detail="not found")
        claims = ClaimRepository(conn)
        serialized = await _serialize_contradiction(contradiction, claims)
    assert serialized is not None
    await maybe_enqueue_revision_synthesis(user_id, contradiction_id, body.classification)
    return serialized
