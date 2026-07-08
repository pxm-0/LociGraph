from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.session import session
from kernel.models import Claim, ClaimConceptEdge, Concept

router = APIRouter()


def serialize_claim(claim: Claim) -> dict[str, Any]:
    return {
        "id": str(claim.id),
        "source_id": str(claim.source_id),
        "observation_id": str(claim.observation_id),
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "assertion_type": claim.assertion_type,
        "confidence": claim.confidence,
        "extraction_method": claim.extraction_method,
        "model_name": claim.model_name,
        "prompt_version": claim.prompt_version,
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
    }


def serialize_edge(edge: ClaimConceptEdge) -> dict[str, Any]:
    return {
        "id": str(edge.id),
        "claim_id": str(edge.claim_id),
        "concept_id": str(edge.concept_id),
        "concept_candidate_id": str(edge.concept_candidate_id),
        "confidence": edge.confidence,
        "created_at": edge.created_at.isoformat(),
    }


async def serialize_concept(concept: Concept, concepts: ConceptRepository) -> dict[str, Any]:
    return {
        "id": str(concept.id),
        "concept_name": concept.concept_name,
        "concept_type": concept.concept_type,
        "description": concept.description,
        "status": concept.status,
        "created_at": concept.created_at.isoformat(),
        "claim_count": await concepts.count_for_concept(concept.id),
    }


@router.get("/concepts")
async def list_concepts(
    concept_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        concepts = ConceptRepository(conn)
        rows = await concepts.list(
            concept_type=concept_type,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [await serialize_concept(concept, concepts) for concept in rows]


@router.get("/concepts/count")
async def count_concepts(
    concept_type: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ConceptRepository(conn).count(concept_type=concept_type, status=status)
    return {"total": total}


@router.get("/concepts/{concept_id}")
async def get_concept(
    concept_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        concepts = ConceptRepository(conn)
        concept = await concepts.get(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="not found")
        return await serialize_concept(concept, concepts)


@router.get("/concepts/{concept_id}/claims")
async def list_concept_claims(
    concept_id: str,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).get(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="not found")
        edges = await ClaimConceptEdgeRepository(conn).list_for_concept(concept_id)
        claims = ClaimRepository(conn)
        result = []
        for edge in edges:
            claim = await claims.get(edge.claim_id)
            if claim is not None:
                result.append(serialize_claim(claim))
        return result
