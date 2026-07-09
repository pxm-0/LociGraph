import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_claim_and_candidate(conn, user_id, source_id):
    [observation_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": "The user cares about careful plans."}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=observation_id,
        claim_text="The user cares about careful plans.",
        claim_type="preference",
        assertion_type="perception",
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
        candidate_name="Careful Plans",
        concept_type="idea",
        rationale="Preference topic",
        confidence=0.82,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    return claim, candidate


@pytest.mark.asyncio
async def test_concept_and_edge_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "concepts-repo-1")
        claim, candidate = await _make_claim_and_candidate(conn, user_id, source.id)

        concept_repo = ConceptRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)

        concept = await concept_repo.create(
            user_id=user_id,
            concept_name="Careful Plans",
            concept_type="idea",
            description="A recurring preference.",
        )
        assert concept is not None
        assert concept.status == "active"

        edge = await edge_repo.create(
            user_id=user_id,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.82,
        )
        assert edge is not None

        fetched_concept = await concept_repo.get(concept.id)
        fetched_edge = await edge_repo.get(edge.id)
        by_name = await concept_repo.find_by_name("idea", "careful plans")
        edges_for_claim = await edge_repo.list_for_claim(claim.id)
        edges_for_concept = await edge_repo.list_for_concept(concept.id)

    assert fetched_concept == concept
    assert fetched_edge == edge
    assert by_name is not None
    assert by_name.id == concept.id
    assert [e.id for e in edges_for_claim] == [edge.id]
    assert [e.id for e in edges_for_concept] == [edge.id]


@pytest.mark.asyncio
async def test_concept_create_is_idempotent_for_case_insensitive_name(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = ConceptRepository(conn)
        first = await repo.create(
            user_id=user_id, concept_name="Careful Plans", concept_type="idea"
        )
        second = await repo.create(
            user_id=user_id, concept_name="careful plans", concept_type="idea"
        )
        concepts = await repo.list(concept_type="idea")

    assert first is not None
    assert second is None
    assert len(concepts) == 1


@pytest.mark.asyncio
async def test_edge_create_is_idempotent_for_same_claim_and_concept(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "concepts-repo-2")
        claim, candidate = await _make_claim_and_candidate(conn, user_id, source.id)

        concept_repo = ConceptRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        concept = await concept_repo.create(
            user_id=user_id, concept_name="Careful Plans", concept_type="idea"
        )
        assert concept is not None

        kwargs = {
            "user_id": user_id,
            "claim_id": claim.id,
            "concept_id": concept.id,
            "concept_candidate_id": candidate.id,
            "confidence": 0.82,
        }
        first = await edge_repo.create(**kwargs)
        second = await edge_repo.create(**kwargs)
        edges = await edge_repo.list_for_claim(claim.id)

    assert first is not None
    assert second is None
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_count_respects_filters(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = ConceptRepository(conn)
        await repo.create(user_id=user_id, concept_name="Careful Plans", concept_type="idea")
        await repo.create(user_id=user_id, concept_name="Bob", concept_type="person")

        total = await repo.count()
        ideas = await repo.count(concept_type="idea")
        none_match = await repo.count(concept_type="place")

    assert total == 2  # noqa: PLR2004
    assert ideas == 1
    assert none_match == 0


@pytest.mark.asyncio
async def test_search_by_name_matches_substring_case_insensitively(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = ConceptRepository(conn)
        await repo.create(
            user_id=user_id, concept_name="Sovereignty", concept_type="value"
        )
        await repo.create(
            user_id=user_id, concept_name="Personal Sovereignty", concept_type="value"
        )
        await repo.create(user_id=user_id, concept_name="Unrelated", concept_type="idea")

        matches = await repo.search_by_name("sovereign")

    assert {c.concept_name for c in matches} == {"Sovereignty", "Personal Sovereignty"}


@pytest.mark.asyncio
async def test_search_by_name_respects_limit(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = ConceptRepository(conn)
        for i in range(3):
            await repo.create(
                user_id=user_id, concept_name=f"Topic {i}", concept_type="idea"
            )

        matches = await repo.search_by_name("Topic", limit=2)

    assert len(matches) == 2
