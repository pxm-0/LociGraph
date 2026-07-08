from __future__ import annotations

import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.embed_claims import _embed_claims, _heal_embed_claims, embed_claims
from worker.tasks.healing import MAX_HEAL_GENERATIONS


def _pad_vector(v: list[float]) -> list[float]:
    """Pad a vector to 1536 dimensions for pgvector."""
    return v + [0.0] * (1536 - len(v))


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        self.calls.append(list(texts))
        return [_pad_vector([float(len(t)), 0.0]) for t in texts]


async def _seed_source_with_claims(user_id, count=1):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "embed-worker")
        await SourceRepository(conn).mark_verified(source.id)
        claim_repo = ClaimRepository(conn)
        claims = []
        for i in range(count):
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": f"Alpha {i} matters."}], source.id, user_id
            )
            claim = await claim_repo.create(
                user_id=user_id,
                source_id=source.id,
                observation_id=obs_id,
                claim_text=f"Alpha {i} matters.",
                claim_type="fact",
                assertion_type="reality",
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            assert claim is not None
            claims.append(claim)
        job = await JobRepository(conn).create(
            user_id, "embed_claims", payload={"source_id": str(source.id)}
        )
    return source, claims, job


@pytest.mark.asyncio
async def test_embed_claims_creates_a_vector_per_pending_claim(make_user, monkeypatch):
    user_id = await make_user()
    source, claims, job = await _seed_source_with_claims(user_id, count=2)
    fake = FakeEmbedder()
    monkeypatch.setattr("worker.tasks.embed_claims.get_embedder", lambda settings: fake)

    await _embed_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        vector_repo = SemanticVectorRepository(conn)
        vectors = [await vector_repo.get_for_claim(c.id) for c in claims]
        done = await JobRepository(conn).get(job.id)

    assert all(v is not None for v in vectors)
    assert done.status == "completed"
    assert done.result == {"embedded": 2}


@pytest.mark.asyncio
async def test_embed_claims_is_idempotent_and_skips_already_embedded(make_user, monkeypatch):
    user_id = await make_user()
    source, claims, job = await _seed_source_with_claims(user_id, count=1)
    fake = FakeEmbedder()
    monkeypatch.setattr("worker.tasks.embed_claims.get_embedder", lambda settings: fake)

    await _embed_claims(str(source.id), str(user_id), str(job.id))
    assert len(fake.calls) == 1

    async with session(user_id) as conn:
        second_job = await JobRepository(conn).create(
            user_id, "embed_claims", payload={"source_id": str(source.id)}
        )
    await _embed_claims(str(source.id), str(user_id), str(second_job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(second_job.id)
    assert done.result == {"embedded": 0}
    assert len(fake.calls) == 1  # second run found nothing pending, never called the embedder


@pytest.mark.asyncio
async def test_embed_claims_provider_error_fails_job_and_redacts_key(make_user, monkeypatch):
    class BrokenEmbedder:
        async def embed(self, texts):  # type: ignore[no-untyped-def]
            raise ValueError("Incorrect API key provided: sk-abc123secret")

    user_id = await make_user()
    source, _claims, job = await _seed_source_with_claims(user_id, count=1)
    monkeypatch.setattr(
        "worker.tasks.embed_claims.get_embedder", lambda settings: BrokenEmbedder()
    )

    with pytest.raises(ValueError):
        await _embed_claims(str(source.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed = await JobRepository(conn).get(job.id)
    assert failed.status == "failed"
    assert "sk-abc123secret" not in failed.error
    assert failed.error == "OpenAI rejected the configured API key"


def test_embed_claims_wired_to_heal_on_retry_exhausted():
    assert embed_claims.options.get("on_retry_exhausted") == "heal_embed_claims"


@pytest.mark.asyncio
async def test_heal_embed_claims_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    source, _claims, job = await _seed_source_with_claims(user_id, count=1)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.embed_claims.embed_claims.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(source.id), str(user_id), str(job.id)),
        "options": {},
    }
    await _heal_embed_claims(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    new_source_id, new_user_id, new_job_id = sent["args"]
    assert new_source_id == str(source.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_embed_claims_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    source, _claims, job = await _seed_source_with_claims(user_id, count=1)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.embed_claims.embed_claims.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(source.id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_embed_claims(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
