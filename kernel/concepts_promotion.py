from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.models import ClaimConceptEdge, Concept


class CandidateNotPromotable(Exception):
    """Raised when a candidate can't be approved: missing, invisible to this
    tenant (RLS), or already rejected. Task 3 (API) catches this to decide
    the HTTP status (404 for not-found, 409 for a status conflict)."""


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    concept: Concept
    edge: ClaimConceptEdge


async def approve_candidate(conn: AsyncConnection, candidate_id: str | UUID) -> ApprovalResult:
    """Promote a proposed concept candidate: find-or-create its concept, then
    link it to the originating claim via a claim_concept_edges row. Composes
    ConceptCandidateRepository, ConceptRepository, and ClaimConceptEdgeRepository
    over one RLS-scoped conn/transaction (see worker/tasks/extract_claims.py for
    the same multi-repo-over-one-conn shape, minus the Dramatiq/worker plumbing —
    this is a synchronous DB operation, not a background job).

    Idempotent: re-approving an already-accepted candidate returns the existing
    concept + edge rather than erroring or duplicating, since find_or_create and
    edge creation are both dedup-on-conflict.
    """
    candidate_repo = ConceptCandidateRepository(conn)
    concept_repo = ConceptRepository(conn)
    edge_repo = ClaimConceptEdgeRepository(conn)

    candidate = await candidate_repo.get(candidate_id)
    if candidate is None:
        raise CandidateNotPromotable(f"concept candidate {candidate_id} not found")
    if candidate.status not in ("proposed", "accepted"):
        raise CandidateNotPromotable(
            f"concept candidate {candidate_id} has status {candidate.status!r}, "
            "expected 'proposed' or already-'accepted'"
        )

    concept = await concept_repo.find_or_create(
        user_id=candidate.user_id,
        concept_type=candidate.concept_type,
        concept_name=candidate.candidate_name,
        description=candidate.rationale,
    )

    edge = await edge_repo.create(
        user_id=candidate.user_id,
        claim_id=candidate.claim_id,
        concept_id=concept.id,
        concept_candidate_id=candidate.id,
        confidence=candidate.confidence,
    )
    if edge is None:
        edges = await edge_repo.list_for_claim(candidate.claim_id)
        edge = next(e for e in edges if e.concept_id == concept.id)

    if candidate.status == "proposed":
        await candidate_repo.mark_status(
            candidate.id, from_status="proposed", to_status="accepted"
        )

    return ApprovalResult(concept=concept, edge=edge)
