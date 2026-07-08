import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_claims_and_concept_candidates_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-repo-1")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "I prefer small careful plans."}], source.id, user_id
        )
        claim_repo = ClaimRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claim = await claim_repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="The user prefers small careful plans.",
            claim_type="preference",
            assertion_type="perception",
            confidence=0.91,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await candidate_repo.create(
            user_id=user_id,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Careful Plans",
            concept_type="idea",
            rationale="Preference topic",
            confidence=0.82,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

        claims = await claim_repo.list(source_id=source.id, claim_type="preference")
        candidates = await candidate_repo.list(source_id=source.id, status="proposed")

    assert [c.id for c in claims] == [claim.id]
    assert candidates[0].id == candidate.id


@pytest.mark.asyncio
async def test_claim_create_is_idempotent_for_live_text(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-repo-2")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha"}], source.id, user_id
        )
        repo = ClaimRepository(conn)
        kwargs = {
            "user_id": user_id,
            "source_id": source.id,
            "observation_id": observation_id,
            "claim_text": "Alpha is present.",
            "claim_type": "fact",
            "assertion_type": "reality",
            "confidence": 0.8,
            "extraction_method": "test",
            "model_name": "fake",
            "prompt_version": "v1",
        }
        first = await repo.create(**kwargs)
        second = await repo.create(**kwargs)
        claims = await repo.list(source_id=source.id)

    assert first is not None
    assert second is None
    assert len(claims) == 1


@pytest.mark.asyncio
async def test_claim_and_candidate_create_strip_nul_bytes(make_user):
    """Postgres rejects embedded NUL bytes; LLM extraction output occasionally
    contains them (garbled source text) and must not crash the insert."""
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-repo-3")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Beta"}], source.id, user_id
        )
        claim_repo = ClaimRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claim = await claim_repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Beta has a \x00 embedded byte.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
            metadata={"snippet": "trailing\x00garbage"},
        )
        assert claim is not None
        assert "\x00" not in claim.claim_text
        assert "\x00" not in claim.metadata["snippet"]

        candidate = await candidate_repo.create(
            user_id=user_id,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Bad\x00Name",
            concept_type="idea",
            rationale="Rationale\x00text",
            confidence=0.7,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert "\x00" not in candidate.candidate_name
        assert "\x00" not in candidate.rationale


@pytest.mark.asyncio
async def test_count_respects_filters(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-count")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Gamma"}], source.id, user_id
        )
        repo = ClaimRepository(conn)
        await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Gamma is present.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Gamma matters.",
            claim_type="preference",
            assertion_type="perception",
            confidence=0.6,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

        total = await repo.count(source_id=source.id)
        by_type = await repo.count(source_id=source.id, claim_type="preference")
        none_match = await repo.count(source_id=source.id, claim_type="event")

    assert total == 2
    assert by_type == 1
    assert none_match == 0


@pytest.mark.asyncio
async def test_list_for_source_returns_every_claim_unpaginated(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-list-for-source")
        repo = ClaimRepository(conn)
        for i in range(3):
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": f"obs {i}"}], source.id, user_id
            )
            await repo.create(
                user_id=user_id,
                source_id=source.id,
                observation_id=obs_id,
                claim_text=f"claim {i}",
                claim_type="fact",
                assertion_type="reality",
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )

        result = await repo.list_for_source(source.id)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_and_count_filter_by_assertion_type(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-assertion-filter")
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, user_id
        )
        repo = ClaimRepository(conn)
        reality_claim = await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_ids[0],
            claim_text="A fact happened.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_ids[1],
            claim_text="This felt difficult.",
            claim_type="emotion",
            assertion_type="perception",
            confidence=0.7,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

        filtered = await repo.list(source_id=source.id, assertion_type="reality")
        count = await repo.count(source_id=source.id, assertion_type="perception")

    assert reality_claim is not None
    assert reality_claim.assertion_type == "reality"
    assert [c.id for c in filtered] == [reality_claim.id]
    assert count == 1
