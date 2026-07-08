from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.observations import ObservationRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_claim_linked_to_concept(conn, user_id, source_id, concept_id, content):  # type: ignore[no-untyped-def]
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": content}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=obs_id,
        claim_text=content,
        claim_type="fact",
        assertion_type="reality",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    assert claim is not None
    candidate = await ConceptCandidateRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        claim_id=claim.id,
        candidate_name="Test Concept",
        concept_type="idea",
        rationale=None,
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    await ClaimConceptEdgeRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        concept_id=concept_id,
        concept_candidate_id=candidate.id,
        confidence=0.9,
    )
    return claim


@pytest.mark.asyncio
async def test_create_and_get_round_trip_manual_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await SourceRepository(conn).create(user_id, "json", "revisions-repo-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id,
            concept_type="idea",
            concept_name="Test Concept",
            description="Original description.",
        )
        repo = RevisionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=concept.description,
            new_description="Updated by hand.",
            rationale="I know better.",
        )
        fetched = await repo.get(created.id)

    assert created.source == "manual"
    assert created.contradiction_id is None
    assert created.previous_description == "Original description."
    assert created.new_description == "Updated by hand."
    assert fetched == created


@pytest.mark.asyncio
async def test_create_with_contradiction_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "revisions-repo-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept B", description=None
        )
        # revisions.contradiction_id has a real FK to contradictions(id), so the
        # test needs a genuine contradiction row, not an arbitrary UUID.
        claim_a = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It rained."
        )
        claim_b = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It was sunny."
        )
        contradiction = await ContradictionRepository(conn).create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.81,
            rationale="Both claims describe the weather at the same time but disagree.",
        )
        repo = RevisionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id=contradiction.id,
            source="llm_synthesis",
            previous_description=None,
            new_description="Synthesized text.",
            rationale="Claims evolved understanding.",
        )

    assert created.source == "llm_synthesis"
    assert created.contradiction_id == contradiction.id
    assert created.previous_description is None


@pytest.mark.asyncio
async def test_list_and_count_scoped_to_concept_newest_first(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept_a = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept A", description=None
        )
        concept_b = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept C", description=None
        )

    # Separate transactions so Postgres' now() (stable within one transaction)
    # actually differs between them, giving a real created_at order.
    async with session(user_id) as conn:
        first = await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept_a.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="First revision.",
            rationale=None,
        )
    async with session(user_id) as conn:
        second = await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept_a.id,
            contradiction_id=None,
            source="manual",
            previous_description="First revision.",
            new_description="Second revision.",
            rationale=None,
        )
    async with session(user_id) as conn:
        await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept_b.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Unrelated concept's revision.",
            rationale=None,
        )

    async with session(user_id) as conn:
        repo = RevisionRepository(conn)
        revisions = await repo.list(concept_id=concept_a.id)
        count = await repo.count(concept_id=concept_a.id)

    assert [r.id for r in revisions] == [second.id, first.id]
    assert count == 2


@pytest.mark.asyncio
async def test_update_description_changes_concept_and_returns_it(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept D", description="Old."
        )
        repo = ConceptRepository(conn)

        updated = await repo.update_description(concept.id, "New.")
        fetched = await repo.get(concept.id)

    assert updated is not None
    assert updated.description == "New."
    assert fetched.description == "New."
