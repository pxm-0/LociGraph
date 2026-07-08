from __future__ import annotations

import pytest

from kernel.ai.claim_extraction import (
    ClaimExtractionResult,
    ExtractedClaim,
    ExtractedConceptCandidate,
)
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.extract_claims import (
    _extract_claims,
    _heal_extract_claims,
    _public_error,
    dispatch_claim_extraction_jobs,
    extract_claims,
    plan_claim_extraction_jobs,
)
from worker.tasks.healing import MAX_HEAL_GENERATIONS


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
                    assertion_type="reality",
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


def test_extract_claims_has_a_generous_time_limit():
    # dramatiq's default 10-minute limit can't fit thousands of sequential
    # batches for a large source; must be raised well beyond the default.
    ten_minutes_ms = 10 * 60 * 1000
    assert extract_claims.options.get("time_limit", ten_minutes_ms) > ten_minutes_ms


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
    new_source_id, new_user_id, new_job_id, new_force, new_observation_ids = sent["args"]
    assert new_source_id == str(source.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)
    assert new_force is False
    # legacy 4-arg message (pre-dating chunking) carries no observation_ids;
    # None routes the healed job back through the full-source legacy path.
    assert new_observation_ids is None

    async with session(user_id) as conn:
        new_job = await JobRepository(conn).get(new_job_id)
    assert new_job is not None
    assert new_job.job_type == "extract_claims"


@pytest.mark.asyncio
async def test_heal_extract_claims_preserves_the_chunk_observation_ids(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.extract_claims.extract_claims.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    chunk = ["11111111-1111-1111-1111-111111111111"]
    original_message = {
        "args": (str(source.id), str(user_id), str(job.id), False, chunk),
        "options": {},
    }
    await _heal_extract_claims(original_message, {"retries": 3, "max_retries": 3})

    *_, new_observation_ids = sent["args"]
    assert new_observation_ids == chunk


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


@pytest.mark.asyncio
async def test_plan_claim_extraction_jobs_splits_into_chunks(make_user, monkeypatch):
    monkeypatch.setattr("worker.tasks.extract_claims.MAX_OBSERVATIONS_PER_JOB", 3)
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "chunk-source")
        await SourceRepository(conn).mark_verified(source.id)
        await ObservationRepository(conn).bulk_insert(
            [{"content": f"obs {i}"} for i in range(7)], source.id, user_id
        )
        jobs = await plan_claim_extraction_jobs(conn, str(source.id), str(user_id))

    assert [len(ids) for _, ids in jobs] == [3, 3, 1]
    assert len({job_id for job_id, _ in jobs}) == 3  # one distinct job per chunk
    all_ids = {oid for _, ids in jobs for oid in ids}
    assert len(all_ids) == 7  # every observation covered exactly once, no overlap


@pytest.mark.asyncio
async def test_plan_claim_extraction_jobs_single_chunk_when_under_the_limit(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "small-source")
        await SourceRepository(conn).mark_verified(source.id)
        await ObservationRepository(conn).bulk_insert([{"content": "only one"}], source.id, user_id)
        jobs = await plan_claim_extraction_jobs(conn, str(source.id), str(user_id))

    assert len(jobs) == 1
    assert len(jobs[0][1]) == 1


@pytest.mark.asyncio
async def test_plan_claim_extraction_jobs_creates_a_noop_job_when_nothing_pending(
    make_user, monkeypatch
):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    await _extract_claims(str(source.id), str(user_id), str(job.id))  # claims the only observation

    async with session(user_id) as conn:
        jobs = await plan_claim_extraction_jobs(conn, str(source.id), str(user_id))

    assert len(jobs) == 1
    assert jobs[0][1] == []


@pytest.mark.asyncio
async def test_plan_claim_extraction_jobs_force_wipes_claims_once_up_front(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        jobs = await plan_claim_extraction_jobs(conn, str(source.id), str(user_id), force=True)
        claims = await ClaimRepository(conn).list(source_id=source.id)

    assert claims == []  # wiped once at plan time, not deferred to a chunk job
    assert len(jobs[0][1]) == 1  # the one observation is pending again under force


@pytest.mark.asyncio
async def test_dispatch_claim_extraction_jobs_sends_one_message_per_chunk(make_user, monkeypatch):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "dispatch-source")
        await SourceRepository(conn).mark_verified(source.id)
        await ObservationRepository(conn).bulk_insert(
            [{"content": "x"}, {"content": "y"}], source.id, user_id
        )
        jobs = await plan_claim_extraction_jobs(conn, str(source.id), str(user_id))

    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.extract_claims.send",
        lambda *args: sent.append(args),
    )
    dispatch_claim_extraction_jobs(jobs, str(source.id), str(user_id), False)

    assert len(sent) == len(jobs)


@pytest.mark.asyncio
async def test_extract_claims_with_explicit_ids_only_processes_that_chunk(make_user, monkeypatch):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "chunk-isolation")
        await SourceRepository(conn).mark_verified(source.id)
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "in chunk"}, {"content": "not in chunk"}], source.id, user_id
        )
        job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id)}
        )
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )

    await _extract_claims(
        str(source.id), str(user_id), str(job.id), observation_ids=[str(obs_ids[0])]
    )

    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(source_id=source.id)
        done = await JobRepository(conn).get(job.id)

    assert [c.observation_id for c in claims] == [obs_ids[0]]
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_extract_claims_with_explicit_ids_ignores_sibling_jobs(make_user, monkeypatch):
    # Chunked jobs for the same source run concurrently by design — the
    # duplicate-in-progress guard only applies to the legacy full-source path.
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    async with session(user_id) as conn:
        sibling = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": str(source.id)}
        )
        await JobRepository(conn).mark_running(sibling.id)
        observations = await ObservationRepository(conn).list_for_source(source.id)

    await _extract_claims(
        str(source.id), str(user_id), str(job.id), observation_ids=[str(observations[0].id)]
    )

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
        claims = await ClaimRepository(conn).list(source_id=source.id)

    assert done.status == "completed"
    assert len(claims) == 1  # ran for real, wasn't skipped as a "duplicate"


@pytest.mark.asyncio
async def test_extract_claims_auto_promotes_candidates_to_concepts(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        candidates = await ConceptCandidateRepository(conn).list(source_id=source.id)
        concepts = await ConceptRepository(conn).list()

    assert candidates[0].status == "accepted"
    assert any(c.concept_name == "Alpha" for c in concepts)


@pytest.mark.asyncio
async def test_extract_claims_auto_enqueues_embedding_when_flag_set(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setenv("EMBEDDING_AUTORUN", "true")
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.embed_claims.send",
        lambda *args: sent.append(args),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    assert len(sent) == 1
    sent_source_id, sent_user_id, _sent_job_id = sent[0]
    assert sent_source_id == str(source.id)
    assert sent_user_id == str(user_id)


@pytest.mark.asyncio
async def test_extract_claims_does_not_enqueue_embedding_when_flag_unset(make_user, monkeypatch):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.delenv("EMBEDDING_AUTORUN", raising=False)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.embed_claims.send",
        lambda *args: sent.append(args),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    assert sent == []


@pytest.mark.asyncio
async def test_extract_claims_stays_completed_when_embed_enqueue_fails(make_user, monkeypatch):
    # A broker/config failure while auto-enqueuing embed_claims must not
    # corrupt the extraction job's already-committed 'completed' state or
    # lose its real result counts — regression test for a bug where the
    # enqueue lived inside the extraction's own try/except.
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setenv("EMBEDDING_AUTORUN", "true")
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    monkeypatch.setattr(
        "worker.tasks.extract_claims.embed_claims.send",
        lambda *args: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
        claims = await ClaimRepository(conn).list(source_id=source.id)

    assert done.status == "completed"
    assert done.result["claims"] == 1
    assert done.error is None
    assert len(claims) == 1
