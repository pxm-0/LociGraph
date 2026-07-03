from __future__ import annotations

import pytest

from kernel.ai.claim_extraction import (
    ClaimExtractionResult,
    ExtractedClaim,
    ExtractedConceptCandidate,
)
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.extract_claims import (
    MAX_HEAL_GENERATIONS,
    _extract_claims,
    _heal_extract_claims,
    _public_error,
    extract_claims,
)


class FakeExtractor:
    def __init__(self, claim_text: str = "Alpha matters.") -> None:
        self.claim_text = claim_text

    async def extract(self, observations):  # type: ignore[no-untyped-def]
        return ClaimExtractionResult(
            claims=[
                ExtractedClaim(
                    observation_id=observations[0].id,
                    claim_text=self.claim_text,
                    claim_type="fact",
                    confidence=0.88,
                    concept_candidates=[
                        ExtractedConceptCandidate(
                            candidate_name="Alpha",
                            concept_type="idea",
                            confidence=0.72,
                            rationale="Primary term",
                        )
                    ],
                )
            ],
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )


def test_public_error_redacts_openai_api_key_fragments():
    message = (
        "Incorrect API key provided: sk-abc123*************xyz. "
        "You can find your API key at https://platform.openai.com/account/api-keys."
    )
    assert _public_error(message) == "OpenAI rejected the configured API key"


async def _seed_verified_source(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "extract-worker")
        await SourceRepository(conn).mark_verified(source.id)
        await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha matters."}], source.id, user_id
        )
        job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id)}
        )
    return source, job


@pytest.mark.asyncio
async def test_extract_claims_persists_claims_and_candidates(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(source_id=source.id)
        candidates = await ConceptCandidateRepository(conn).list(source_id=source.id)
        done = await JobRepository(conn).get(job.id)

    assert len(claims) == 1
    assert len(candidates) == 1
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_extract_claims_tracks_progress(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)

    assert done.items_completed == 1
    assert done.items_total == 1


@pytest.mark.asyncio
async def test_extract_claims_is_idempotent_by_default(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))
    async with session(user_id) as conn:
        second_job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id)}
        )
    await _extract_claims(str(source.id), str(user_id), str(second_job.id))

    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(source_id=source.id)
        done = await JobRepository(conn).get(second_job.id)

    assert len(claims) == 1
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_extract_claims_force_replaces_proposed_claims(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor("Alpha matters."),
    )
    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        second_job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id), "force": True}
        )
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor("Alpha is important."),
    )
    await _extract_claims(str(source.id), str(user_id), str(second_job.id), force=True)

    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(source_id=source.id)

    assert [claim.claim_text for claim in claims] == ["Alpha is important."]


@pytest.mark.asyncio
async def test_extract_claims_missing_provider_config_fails_job(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "openai")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed = await JobRepository(conn).get(job.id)
    assert failed.status == "failed"


@pytest.mark.asyncio
async def test_extract_claims_provider_error_fails_job(make_user, monkeypatch):
    class BrokenExtractor:
        async def extract(self, observations):  # type: ignore[no-untyped-def]
            raise ValueError("bad schema")

    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: BrokenExtractor(),
    )

    with pytest.raises(ValueError, match="bad schema"):
        await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed = await JobRepository(conn).get(job.id)
    assert failed.status == "failed"


@pytest.mark.asyncio
async def test_extract_claims_skips_when_another_job_already_active(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    extractor_calls = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: extractor_calls.append(1) or FakeExtractor(),
    )

    async with session(user_id) as conn:
        other_job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id), "force": False}
        )
        await JobRepository(conn).mark_running(other_job.id)

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    assert extractor_calls == []  # never attempted extraction
    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
        claims = await ClaimRepository(conn).list(source_id=source.id)
    assert done.status == "completed"
    assert claims == []


def test_extract_claims_wired_to_heal_on_retry_exhausted():
    assert extract_claims.options.get("on_retry_exhausted") == "heal_extract_claims"


@pytest.mark.asyncio
async def test_heal_extract_claims_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    sent: dict = {}

    def fake_send_with_options(*, args, delay, heal_generation):
        sent["args"] = args
        sent["delay"] = delay
        sent["heal_generation"] = heal_generation

    monkeypatch.setattr(
        "worker.tasks.extract_claims.extract_claims.send_with_options",
        fake_send_with_options,
    )

    original_message = {
        "args": (str(source.id), str(user_id), str(job.id), False),
        "options": {},
    }
    await _heal_extract_claims(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    assert sent["delay"] > 0
    new_source_id, new_user_id, new_job_id, new_force = sent["args"]
    assert new_source_id == str(source.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)
    assert new_force is False

    async with session(user_id) as conn:
        new_job = await JobRepository(conn).get(new_job_id)
    assert new_job is not None
    assert new_job.job_type == "extract_claims"


@pytest.mark.asyncio
async def test_heal_extract_claims_increments_generation_each_time(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.extract_claims.extract_claims.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(source.id), str(user_id), str(job.id), False),
        "options": {"heal_generation": 2},
    }
    await _heal_extract_claims(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 3


@pytest.mark.asyncio
async def test_heal_extract_claims_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.extract_claims.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(source.id), str(user_id), str(job.id), False),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_extract_claims(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
