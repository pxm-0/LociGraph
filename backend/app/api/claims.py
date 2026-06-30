from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.session import session
from kernel.models import Claim, ConceptCandidate

router = APIRouter()


def _serialize_claim(claim: Claim) -> dict[str, Any]:
    return {
        "id": str(claim.id),
        "source_id": str(claim.source_id),
        "observation_id": str(claim.observation_id),
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "extraction_method": claim.extraction_method,
        "model_name": claim.model_name,
        "prompt_version": claim.prompt_version,
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
    }


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
    return [_serialize_claim(claim) for claim in claims]


@router.get("/claims/{claim_id}")
async def get_claim(
    claim_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        claim = await ClaimRepository(conn).get(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="not found")
    return _serialize_claim(claim)


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
