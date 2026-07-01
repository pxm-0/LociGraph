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
