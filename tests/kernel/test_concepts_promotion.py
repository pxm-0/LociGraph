import pytest

from kernel.concepts_promotion import CandidateNotPromotable, approve_candidate
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_candidate(conn, user_id, source_id, *, candidate_name="Careful Plans"):
    [observation_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": "The user cares about careful plans."}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=observation_id,
        claim_text="The user cares about careful plans.",
        claim_type="preference",
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
        candidate_name=candidate_name,
        concept_type="idea",
        rationale="Preference topic",
        confidence=0.82,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    return claim, candidate


@pytest.mark.asyncio
async def test_approve_dedups_concept_across_two_candidates_same_name_and_type(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "promo-1")
        _claim1, candidate1 = await _make_candidate(conn, user_id, source.id)
        _claim2, candidate2 = await _make_candidate(
            conn, user_id, source.id, candidate_name="careful plans"
        )

        result1 = await approve_candidate(conn, candidate1.id)
        result2 = await approve_candidate(conn, candidate2.id)

        concepts = await ConceptRepository(conn).list(concept_type="idea")

    assert result1.concept.id == result2.concept.id
    assert result1.edge.id != result2.edge.id
    assert len(concepts) == 1


@pytest.mark.asyncio
async def test_reject_leaves_no_concept_or_edge(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "promo-2")
        _claim, candidate = await _make_candidate(conn, user_id, source.id)

        rejected = await ConceptCandidateRepository(conn).reject(candidate.id)

        concepts = await ConceptRepository(conn).list(concept_type="idea")
        edges = await ClaimConceptEdgeRepository(conn).list_for_claim(_claim.id)

    assert rejected is not None
    assert rejected.status == "rejected"
    assert concepts == []
    assert edges == []


@pytest.mark.asyncio
async def test_approve_is_idempotent_on_reapproval(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "promo-3")
        _claim, candidate = await _make_candidate(conn, user_id, source.id)

        first = await approve_candidate(conn, candidate.id)
        second = await approve_candidate(conn, candidate.id)

        concepts = await ConceptRepository(conn).list(concept_type="idea")
        edges = await ClaimConceptEdgeRepository(conn).list_for_claim(_claim.id)
        recandidate = await ConceptCandidateRepository(conn).get(candidate.id)

    assert first.concept.id == second.concept.id
    assert first.edge.id == second.edge.id
    assert len(concepts) == 1
    assert len(edges) == 1
    assert recandidate is not None
    assert recandidate.status == "accepted"


@pytest.mark.asyncio
async def test_approve_rejects_a_rejected_candidate(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "promo-4")
        _claim, candidate = await _make_candidate(conn, user_id, source.id)
        await ConceptCandidateRepository(conn).reject(candidate.id)

        with pytest.raises(CandidateNotPromotable) as exc_info:
            await approve_candidate(conn, candidate.id)
        assert exc_info.value.reason == "invalid_status"


@pytest.mark.asyncio
async def test_cannot_approve_another_users_candidate(make_user):
    owner_id = await make_user()
    other_id = await make_user()
    async with session(owner_id) as conn:
        source = await SourceRepository(conn).create(owner_id, "json", "promo-5")
        _claim, candidate = await _make_candidate(conn, owner_id, source.id)

    async with session(other_id) as conn:
        with pytest.raises(CandidateNotPromotable) as exc_info:
            await approve_candidate(conn, candidate.id)
        assert exc_info.value.reason == "not_found"


@pytest.mark.asyncio
async def test_cannot_reject_another_users_candidate(make_user):
    owner_id = await make_user()
    other_id = await make_user()
    async with session(owner_id) as conn:
        source = await SourceRepository(conn).create(owner_id, "json", "promo-6")
        _claim, candidate = await _make_candidate(conn, owner_id, source.id)

    async with session(other_id) as conn:
        rejected = await ConceptCandidateRepository(conn).reject(candidate.id)

    assert rejected is None
