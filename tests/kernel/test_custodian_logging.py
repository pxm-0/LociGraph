from __future__ import annotations

import pytest

from kernel.custodian_logging import (
    LoggedItemNotResolvable,
    accept_logged_item,
    get_or_create_custodian_source,
    reject_logged_item,
)
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.custodian import CustodianRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.notes import NoteRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_session(conn, user_id):  # type: ignore[no-untyped-def]
    return await CustodianRepository(conn).create_session(
        user_id=user_id, model="gpt-4o-mini", provider="openai"
    )


async def _propose(conn, user_id, session_id, item_type, content, target_id=None):  # type: ignore[no-untyped-def]
    return await CustodianLoggedItemRepository(conn).create(
        user_id=user_id, session_id=session_id, item_type=item_type, content=content,
        target_id=target_id,
    )


@pytest.mark.asyncio
async def test_accept_observation_creates_a_sourceless_observation(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "observation", {"content": "It rained."}
        )
        accepted = await accept_logged_item(conn, item.id)
        observation = await ObservationRepository(conn).list(limit=10)

    assert accepted.status == "accepted"
    assert accepted.target_id is not None
    assert observation[0].content == "It rained."
    assert observation[0].source_id is None


@pytest.mark.asyncio
async def test_accept_note_creates_a_note(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "note", {"content": "Remember this."}
        )
        accepted = await accept_logged_item(conn, item.id)
        note = await NoteRepository(conn).get(accepted.target_id)

    assert note is not None
    assert note.content == "Remember this."


@pytest.mark.asyncio
async def test_accept_claim_creates_observation_and_claim_on_custodian_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "claim",
            {"claim_text": "The sky is blue.", "claim_type": "fact", "assertion_type": "reality"},
        )
        accepted = await accept_logged_item(conn, item.id)
        claim = await ClaimRepository(conn).get(accepted.target_id)
        source = await get_or_create_custodian_source(conn, user_id)

    assert claim is not None
    assert claim.claim_text == "The sky is blue."
    assert claim.source_id == source.id


@pytest.mark.asyncio
async def test_accept_task_fixes_claim_type_and_assertion_type(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "task", {"claim_text": "Call the vet."}
        )
        accepted = await accept_logged_item(conn, item.id)
        claim = await ClaimRepository(conn).get(accepted.target_id)

    assert claim is not None
    assert claim.claim_type == "task"
    assert claim.assertion_type == "reality"


@pytest.mark.asyncio
async def test_accept_concept_candidate_uses_target_claims_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "logging-cc-1")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Freedom matters."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_id,
            claim_text="Freedom matters.", claim_type="belief", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim is not None
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "concept_candidate",
            {"candidate_name": "Sovereignty", "concept_type": "value", "rationale": None},
            target_id=claim.id,
        )
        accepted = await accept_logged_item(conn, item.id)
        candidate = await ConceptCandidateRepository(conn).get(accepted.target_id)

    assert candidate is not None
    assert candidate.candidate_name == "Sovereignty"
    assert candidate.source_id == source.id


@pytest.mark.asyncio
async def test_accept_reality_assertion_retags_the_claim(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "logging-ra-1")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It felt cold."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_id,
            claim_text="It felt cold.", claim_type="fact", assertion_type="interpretation",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim is not None
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "reality_assertion", {}, target_id=claim.id
        )
        await accept_logged_item(conn, item.id)
        updated = await ClaimRepository(conn).get(claim.id)

    assert updated is not None
    assert updated.assertion_type == "reality"


@pytest.mark.asyncio
async def test_accept_contradiction_requires_shared_concept(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "logging-contra-1")
        [obs_a, obs_b] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}, {"content": "It was sunny."}], source.id, user_id
        )
        claim_a = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_a,
            claim_text="It rained.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        claim_b = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_b,
            claim_text="It was sunny.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim_a is not None and claim_b is not None
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "contradiction",
            {
                "claim_b_id": str(claim_b.id),
                "concept_id": "00000000-0000-0000-0000-000000000000",
                "rationale": "They disagree.",
            },
            target_id=claim_a.id,
        )

        with pytest.raises(LoggedItemNotResolvable) as exc_info:
            await accept_logged_item(conn, item.id)

    assert exc_info.value.reason == "concept_mismatch"


@pytest.mark.asyncio
async def test_accept_contradiction_succeeds_when_both_claims_share_the_concept(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "logging-contra-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Weather", description=None
        )
        [obs_a, obs_b] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}, {"content": "It was sunny."}], source.id, user_id
        )
        claim_a = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_a,
            claim_text="It rained.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        claim_b = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_b,
            claim_text="It was sunny.", claim_type="fact", assertion_type="reality",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim_a is not None and claim_b is not None
        candidate_repo = ConceptCandidateRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        for claim in (claim_a, claim_b):
            candidate = await candidate_repo.create(
                user_id=user_id, source_id=source.id, claim_id=claim.id,
                candidate_name="Weather", concept_type="idea", rationale=None,
                confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
            )
            await edge_repo.create(
                user_id=user_id, claim_id=claim.id, concept_id=concept.id,
                concept_candidate_id=candidate.id, confidence=0.9,
            )
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "contradiction",
            {
                "claim_b_id": str(claim_b.id),
                "concept_id": str(concept.id),
                "rationale": "They disagree.",
            },
            target_id=claim_a.id,
        )
        accepted = await accept_logged_item(conn, item.id)

    assert accepted.status == "accepted"
    assert accepted.target_id is not None


@pytest.mark.asyncio
async def test_accept_importance_signal(make_user):
    from uuid import uuid4

    user_id = await make_user()
    target_id = uuid4()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "importance_signal",
            {"target_type": "claim"}, target_id=target_id,
        )
        accepted = await accept_logged_item(conn, item.id)
        signals = await ImportanceSignalRepository(conn).list_for_target("claim", target_id)

    assert accepted.status == "accepted"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_accept_raises_not_found_for_unknown_item(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        with pytest.raises(LoggedItemNotResolvable) as exc_info:
            await accept_logged_item(conn, "00000000-0000-0000-0000-000000000000")

    assert exc_info.value.reason == "not_found"


@pytest.mark.asyncio
async def test_reject_sets_status_and_is_not_re_resolvable(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        item = await _propose(
            conn, user_id, custodian_session.id, "note", {"content": "x"}
        )
        rejected = await reject_logged_item(conn, item.id)

        with pytest.raises(LoggedItemNotResolvable) as exc_info:
            await accept_logged_item(conn, item.id)

    assert rejected.status == "rejected"
    assert exc_info.value.reason == "invalid_status"


@pytest.mark.asyncio
async def test_get_or_create_custodian_source_is_reused(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        first = await get_or_create_custodian_source(conn, user_id)
        second = await get_or_create_custodian_source(conn, user_id)

    assert first.id == second.id
    assert first.import_status == "VERIFIED"
