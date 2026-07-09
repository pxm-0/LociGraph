from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.notes import NoteRepository
from kernel.db.observations import ObservationRepository
from kernel.db.sources import SourceRepository
from kernel.ingestion.base import SourceType
from kernel.models import CustodianLoggedItem, Source


@dataclass
class LoggedItemNotResolvable(Exception):
    """Raised when a logged item can't be accepted/rejected: missing,
    invisible to this tenant (RLS), already resolved, or (contradiction
    proposals only) the two claims aren't both linked to the stated concept
    yet. The API layer catches this to decide the HTTP status."""

    message: str
    reason: str  # "not_found" | "invalid_status" | "concept_mismatch" | "duplicate"


async def get_or_create_custodian_source(conn: AsyncConnection, user_id: str | UUID) -> Source:
    """One verified 'custodian'-type Source per user, created lazily and
    reused — lets Custodian-created claims satisfy claims.source_id's
    NOT NULL FK without a parallel ingestion pipeline. See
    kernel/ingestion/base.py: this type is deliberately excluded from
    SourceType.ALL (never uploaded, never parsed)."""
    sources = SourceRepository(conn)
    existing = await sources.get_by_type(SourceType.CUSTODIAN)
    if existing is not None:
        return existing
    source = await sources.create(user_id, SourceType.CUSTODIAN, "custodian-source")
    await sources.mark_verified(source.id)
    # mark_verified doesn't return the row, and `source` above is stale
    # (still shows the pre-verify 'PENDING' import_status) — refetch.
    verified = await sources.get(source.id)
    assert verified is not None, "just-created source vanishing mid-call would be a bigger bug"
    return verified


async def _get_or_raise(
    items: CustodianLoggedItemRepository, item_id: str | UUID
) -> CustodianLoggedItem:
    item = await items.get(item_id)
    if item is None:
        raise LoggedItemNotResolvable(
            message=f"logged item {item_id} not found", reason="not_found"
        )
    if item.status != "proposed":
        raise LoggedItemNotResolvable(
            message=f"logged item {item_id} has status {item.status!r}, expected 'proposed'",
            reason="invalid_status",
        )
    return item


async def accept_logged_item(conn: AsyncConnection, item_id: str | UUID) -> CustodianLoggedItem:
    items = CustodianLoggedItemRepository(conn)
    item = await _get_or_raise(items, item_id)
    new_target_id: UUID | None = None

    if item.item_type == "observation":
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [
                {
                    "content": item.content["content"],
                    "speaker": item.content.get("speaker"),
                    "observed_at": item.content.get("observed_at"),
                }
            ],
            None,
            item.user_id,
        )
        new_target_id = obs_id

    elif item.item_type == "note":
        note = await NoteRepository(conn).create(
            user_id=item.user_id, content=item.content["content"]
        )
        new_target_id = note.id

    elif item.item_type in ("claim", "task"):
        source = await get_or_create_custodian_source(conn, item.user_id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": item.content["claim_text"]}], source.id, item.user_id
        )
        claim_type = "task" if item.item_type == "task" else item.content["claim_type"]
        assertion_type = (
            "reality" if item.item_type == "task" else item.content["assertion_type"]
        )
        claim = await ClaimRepository(conn).create(
            user_id=item.user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text=item.content["claim_text"],
            claim_type=claim_type,
            assertion_type=assertion_type,
            confidence=1.0,
            extraction_method="custodian",
            model_name=None,
            prompt_version=None,
        )
        if claim is None:
            raise LoggedItemNotResolvable(message="claim already exists", reason="duplicate")
        new_target_id = claim.id

    elif item.item_type == "concept_candidate":
        assert item.target_id is not None, "concept_candidate proposals must set target_id"
        claim = await ClaimRepository(conn).get(item.target_id)
        if claim is None:
            raise LoggedItemNotResolvable(message="target claim not found", reason="not_found")
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=item.user_id,
            source_id=claim.source_id,
            claim_id=claim.id,
            candidate_name=item.content["candidate_name"],
            concept_type=item.content["concept_type"],
            rationale=item.content.get("rationale"),
            confidence=1.0,
            extraction_method="custodian",
            model_name=None,
            prompt_version=None,
        )
        new_target_id = candidate.id

    elif item.item_type in ("reality_assertion", "perception_assertion"):
        assertion_type = "reality" if item.item_type == "reality_assertion" else "perception"
        assert item.target_id is not None, "reality/perception_assertion needs a target_id"
        updated = await ClaimRepository(conn).set_assertion_type(item.target_id, assertion_type)
        if updated is None:
            raise LoggedItemNotResolvable(message="target claim not found", reason="not_found")

    elif item.item_type == "contradiction":
        assert item.target_id is not None, "contradiction proposals must set target_id (claim A)"
        edges = ClaimConceptEdgeRepository(conn)
        concept_id = item.content["concept_id"]
        claim_b_id = item.content["claim_b_id"]
        a_concepts = {str(e.concept_id) for e in await edges.list_for_claim(item.target_id)}
        b_concepts = {str(e.concept_id) for e in await edges.list_for_claim(claim_b_id)}
        if concept_id not in a_concepts or concept_id not in b_concepts:
            raise LoggedItemNotResolvable(
                message="both claims must already be linked to the given concept",
                reason="concept_mismatch",
            )
        contradiction = await ContradictionRepository(conn).create(
            user_id=item.user_id,
            concept_id=concept_id,
            claim_a_id=item.target_id,
            claim_b_id=claim_b_id,
            similarity=1.0,
            rationale=item.content.get("rationale", ""),
        )
        if contradiction is None:
            raise LoggedItemNotResolvable(
                message="contradiction already exists", reason="duplicate"
            )
        new_target_id = contradiction.id

    elif item.item_type == "importance_signal":
        assert item.target_id is not None, "importance_signal proposals must set target_id"
        signal = await ImportanceSignalRepository(conn).create(
            user_id=item.user_id,
            target_type=item.content["target_type"],
            target_id=item.target_id,
        )
        new_target_id = signal.id

    resolved = await items.resolve(item_id, "accepted", target_id=new_target_id)
    assert resolved is not None, "item was 'proposed' one line above — resolve cannot race here"
    return resolved


async def reject_logged_item(conn: AsyncConnection, item_id: str | UUID) -> CustodianLoggedItem:
    items = CustodianLoggedItemRepository(conn)
    await _get_or_raise(items, item_id)
    resolved = await items.resolve(item_id, "rejected")
    assert resolved is not None, "item was 'proposed' one line above — resolve cannot race here"
    return resolved
