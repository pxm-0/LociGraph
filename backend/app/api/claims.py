from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.concepts import serialize_claim, serialize_concept, serialize_edge
from backend.app.auth.dependencies import get_current_user
from kernel.concepts_promotion import CandidateNotPromotable, approve_candidate
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.session import session
from kernel.models import ConceptCandidate

router = APIRouter()


def _serialize_candidate(candidate: ConceptCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "source_id": str(candidate.source_id),
        "claim_id": str(candidate.claim_id),
        "candidate_name": candidate.candidate_name,
        "concept_type": candidate.concept_type,
        "rationale": candidate.rationale,
        "confidence": candidate.confidence,
        "extraction_method": candidate.extraction_method,
        "model_name": candidate.model_name,
        "prompt_version": candidate.prompt_version,
        "status": candidate.status,
        "created_at": candidate.created_at.isoformat(),
    }


@router.get("/claims")
async def list_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    return [serialize_claim(claim) for claim in claims]


@router.get("/claims/count")
async def count_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ClaimRepository(conn).count(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            status=status,
        )
    return {"total": total}


@router.get("/claims/{claim_id}")
async def get_claim(
    claim_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        claim = await ClaimRepository(conn).get(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="not found")
    return serialize_claim(claim)


@router.get("/concept-candidates")
async def list_concept_candidates(
    source_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        candidates = await ConceptCandidateRepository(conn).list(
            source_id=source_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    return [_serialize_candidate(candidate) for candidate in candidates]


@router.post("/concept-candidates/{candidate_id}/approve")
async def approve_concept_candidate(
    candidate_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            result = await approve_candidate(conn, candidate_id)
        except CandidateNotPromotable as exc:
            status_code = 404 if exc.reason == "not_found" else 409
            raise HTTPException(status_code=status_code, detail=exc.message) from exc
        concept_dict = await serialize_concept(result.concept, ConceptRepository(conn))
    return {
        "concept": concept_dict,
        "edge": serialize_edge(result.edge),
    }


@router.post("/concept-candidates/{candidate_id}/reject")
async def reject_concept_candidate(
    candidate_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        repo = ConceptCandidateRepository(conn)
        candidate = await repo.get(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="not found")
        if candidate.status != "proposed":
            raise HTTPException(
                status_code=409,
                detail=f"concept candidate has status {candidate.status!r}, expected 'proposed'",
            )
        rejected = await repo.reject(candidate_id)
        assert rejected is not None, (
            "status was 'proposed' under the same conn; reject() must succeed"
        )
    return _serialize_candidate(rejected)
