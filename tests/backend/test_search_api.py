from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.claims import ClaimRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


class _FixedEmbedder:
    """Returns the same vector for every input, keyed by a lookup table, so
    ranking in a test is deterministic without calling OpenAI."""

    def __init__(self, table: dict[str, list[float]], default: list[float]) -> None:
        self.table = table
        self.default = default

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return [self.table.get(t, self.default) for t in texts]


@pytest.mark.asyncio
async def test_search_ranks_semantically_close_claim_first(client, seeded_user, monkeypatch):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "search-api-1")
        [close_obs] = await ObservationRepository(conn).bulk_insert(
            [{"content": "close"}], source.id, seeded_user
        )
        [far_obs] = await ObservationRepository(conn).bulk_insert(
            [{"content": "far"}], source.id, seeded_user
        )
        claim_repo = ClaimRepository(conn)
        close_claim = await claim_repo.create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=close_obs,
            claim_text="Close claim.",
            claim_type="fact",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        far_claim = await claim_repo.create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=far_obs,
            claim_text="Far claim.",
            claim_type="fact",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        vector_repo = SemanticVectorRepository(conn)
        # Create 1536-dimensional vectors for pgvector
        close_embedding = [1.0] + [0.0] * 1535
        far_embedding = [0.0] + [1.0] + [0.0] * 1534
        await vector_repo.create(
            user_id=seeded_user,
            claim_id=close_claim.id,
            embedding=close_embedding,
            model_name="test",
        )
        await vector_repo.create(
            user_id=seeded_user,
            claim_id=far_claim.id,
            embedding=far_embedding,
            model_name="test",
        )

    # Create 1536-dimensional embeddings for pgvector
    query_embedding = [1.0] + [0.0] * 1535
    default_embedding = [0.0] * 1536
    fixed = _FixedEmbedder({"query": query_embedding}, default=default_embedding)
    monkeypatch.setattr("backend.app.api.search.get_embedder", lambda settings: fixed)

    await _login(client)
    r = await client.get("/search", params={"q": "query"})

    assert r.status_code == 200
    body = r.json()
    assert body[0]["id"] == str(close_claim.id)
    assert body[0]["similarity"] > body[1]["similarity"]

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM semantic_vectors"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_search_never_returns_another_tenants_claims(
    client, seeded_user, make_user, monkeypatch  # type: ignore[no-untyped-def]
):
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "search-api-2")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "hidden"}], source.id, other_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=other_user,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Hidden claim.",
            claim_type="fact",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        # Create 1536-dimensional embedding
        embedding = [1.0] + [0.0] * 1535
        await SemanticVectorRepository(conn).create(
            user_id=other_user, claim_id=claim.id, embedding=embedding, model_name="test"
        )

    # Create 1536-dimensional embeddings for pgvector
    query_embedding = [1.0] + [0.0] * 1535
    default_embedding = [0.0] * 1536
    fixed = _FixedEmbedder({"query": query_embedding}, default=default_embedding)
    monkeypatch.setattr("backend.app.api.search.get_embedder", lambda settings: fixed)

    await _login(client)
    r = await client.get("/search", params={"q": "query"})

    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_search_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/search", params={"q": "anything"})
    assert r.status_code == 401
