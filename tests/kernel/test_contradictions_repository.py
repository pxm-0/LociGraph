from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.observations import ObservationRepository
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
async def test_create_and_get_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It rained."
        )
        claim_b = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It was sunny."
        )
        repo = ContradictionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.81,
            rationale="Both claims describe the weather at the same time but disagree.",
        )
        fetched = await repo.get(created.id)

    assert created is not None
    assert created.classification == "unresolved"
    assert created.classified_at is None
    assert fetched == created


@pytest.mark.asyncio
async def test_create_dedups_a_reversed_pair(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        repo = ContradictionRepository(conn)

        first = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )
        # Same pair, reversed order, as a second detection run might produce
        # (the "new" claim in one direction is the "candidate" in the other).
        second = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_b.id,
            claim_b_id=claim_a.id,
            similarity=0.8,
            rationale="r2",
        )
        all_rows = await repo.list(concept_id=concept.id)

    assert first is not None
    assert second is None
    assert len(all_rows) == 1
    assert {str(all_rows[0].claim_a_id), str(all_rows[0].claim_b_id)} == {
        str(claim_a.id),
        str(claim_b.id),
    }


@pytest.mark.asyncio
async def test_list_and_count_filter_by_classification(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-3")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        claim_c = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "C.")
        repo = ContradictionRepository(conn)
        first = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )
        await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_c.id,
            similarity=0.8,
            rationale="r2",
        )
        await repo.classify(first.id, "evolution")

        unresolved = await repo.list(concept_id=concept.id, classification="unresolved")
        unresolved_count = await repo.count(concept_id=concept.id, classification="unresolved")
        evolved = await repo.list(concept_id=concept.id, classification="evolution")

    assert len(unresolved) == 1
    assert unresolved_count == 1
    assert [c.id for c in evolved] == [first.id]


@pytest.mark.asyncio
async def test_classify_sets_classification_and_classified_at(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-4")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        repo = ContradictionRepository(conn)
        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )

        classified = await repo.classify(created.id, "true_conflict")

    assert classified is not None
    assert classified.classification == "true_conflict"
    assert classified.classified_at is not None
