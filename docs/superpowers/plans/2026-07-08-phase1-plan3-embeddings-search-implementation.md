# Phase 1 Plan 3: Embeddings & Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate OpenAI embeddings for claims, store them in a new pgvector-backed `semantic_vectors` table, and expose a semantic search endpoint + `/search` page that ranks claims by cosine similarity to a query.

**Architecture:** Mirrors the existing claim-extraction pipeline exactly: a settings/provider module in `kernel/ai/`, a repository in `kernel/db/`, a dramatiq worker actor with the same heal-on-retry-exhausted pattern, a FastAPI endpoint, and a frontend page. Embeddings are keyed 1:1 to claims (`semantic_vectors.claim_id UNIQUE`) and auto-triggered after claim extraction persists claims for a chunk, reusing the idempotent "find rows missing a vector" pattern already proven in this codebase.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries, no ORM), asyncpg, Postgres 16 + pgvector 0.8.3 (HNSW cosine index), dramatiq + Redis, OpenAI `text-embedding-3-small`, Next.js/React/TypeScript frontend, pytest + vitest.

## Global Constraints

- Every new table follows the exact RLS pattern from migrations `0002`/`0003`: `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, a `<table>_user_isolation` policy on `user_id = current_setting('app.current_user_id')::uuid` for both `USING` and `WITH CHECK`, and `GRANT SELECT, INSERT, UPDATE, DELETE ... TO locigraph_app`.
- The next migration revision is `0007` (heads: `0001`→`0002`→`0003`→`0004`→`0005`→`0006`; the original plan draft said `0004`, which is now stale — three migrations landed since it was written).
- pgvector has no asyncpg codec installed in this project: embeddings are passed as their literal text form (`"[0.1,0.2,...]"`) via `CAST(:embedding AS vector)` on write, and read back via `embedding::text` cast to `list[float]` in `from_row`.
- Concept embeddings, hybrid/keyword search, re-ranking, and re-embedding on claim edit are explicitly out of scope for this plan.
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod, matching every existing model in `kernel/models.py`.
- All repository methods take an already-open `AsyncConnection` via `BaseRepository.__init__`; RLS scoping happens implicitly through `kernel/db/session.py`'s `session(user_id)` context manager, never through an explicit `WHERE user_id = ...` clause in application code.

---

### Task 1: Schema foundation — `semantic_vectors` table, model, repository

**Files:**
- Create: `migrations/versions/0007_semantic_vectors.py`
- Modify: `kernel/models.py` (add `SemanticVector`, `SimilarClaim` dataclasses)
- Create: `kernel/db/semantic_vectors.py`
- Modify: `kernel/db/claims.py` (add `list_for_source`)
- Create: `tests/kernel/test_semantic_vectors_repository.py`
- Modify: `tests/kernel/test_tenant_isolation.py` (add semantic-vector isolation test)

**Interfaces:**
- Produces: `SemanticVector` dataclass (`id, user_id, claim_id, model_name, created_at, embedding: list[float]`); `SimilarClaim` dataclass (`claim: Claim, similarity: float`); `SemanticVectorRepository(conn)` with `create(*, user_id, claim_id, embedding, model_name) -> SemanticVector | None`, `get_for_claim(claim_id) -> SemanticVector | None`, `claim_ids_without_vector(source_id) -> set[UUID]`, `search_similar(query_embedding, limit=20) -> list[SimilarClaim]`; `ClaimRepository.list_for_source(source_id) -> list[Claim]` (unpaginated, mirrors `ObservationRepository.list_for_source`).
- Consumes: `kernel/db/base_repository.py`'s `BaseRepository`; `kernel/models.py`'s `Claim`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0007_semantic_vectors.py`:

```python
"""claim embeddings for semantic search

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DATA_TABLES = ["semantic_vectors"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE semantic_vectors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            claim_id UUID NOT NULL UNIQUE REFERENCES claims(id),
            embedding vector(1536) NOT NULL,
            model_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX semantic_vectors_embedding_hnsw_idx ON semantic_vectors "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON semantic_vectors TO locigraph_app"
    )
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS semantic_vectors CASCADE")
```

- [ ] **Step 2: Run the migration and verify it applies cleanly**

Run: `MIGRATION_DATABASE_URL=postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph .venv/bin/alembic upgrade head`
Expected: no errors; `alembic current` reports `0007`.

- [ ] **Step 3: Add `SemanticVector` and `SimilarClaim` to `kernel/models.py`**

Add after the existing `Claim` dataclass (after its `from_row` classmethod, before the next `@dataclass` block):

```python
@dataclass(frozen=True, slots=True)
class SemanticVector:
    id: UUID
    user_id: UUID
    claim_id: UUID
    model_name: str
    created_at: datetime
    embedding: list[float]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SemanticVector:
        raw = row["embedding"]
        parsed = (
            [float(x) for x in raw.strip("[]").split(",")]
            if isinstance(raw, str)
            else list(raw)
        )
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            claim_id=row["claim_id"],
            model_name=row["model_name"],
            created_at=row["created_at"],
            embedding=parsed,
        )


@dataclass(frozen=True, slots=True)
class SimilarClaim:
    claim: Claim
    similarity: float
```

- [ ] **Step 4: Write the failing repository test**

Create `tests/kernel/test_semantic_vectors_repository.py`:

```python
import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_claim(conn, user_id, source_id, content="Alpha matters."):
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": content}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=obs_id,
        claim_text=content,
        claim_type="fact",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    assert claim is not None
    return claim


@pytest.mark.asyncio
async def test_create_and_get_for_claim_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-1")
        claim = await _make_claim(conn, user_id, source.id)
        repo = SemanticVectorRepository(conn)
        vector = [0.1, 0.2, 0.3]

        created = await repo.create(
            user_id=user_id, claim_id=claim.id, embedding=vector, model_name="test-model"
        )
        fetched = await repo.get_for_claim(claim.id)

    assert created is not None
    assert created.embedding == pytest.approx(vector)
    assert created.model_name == "test-model"
    assert fetched == created


@pytest.mark.asyncio
async def test_create_is_idempotent_for_same_claim(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-2")
        claim = await _make_claim(conn, user_id, source.id)
        repo = SemanticVectorRepository(conn)

        first = await repo.create(
            user_id=user_id, claim_id=claim.id, embedding=[0.1, 0.2], model_name="test-model"
        )
        second = await repo.create(
            user_id=user_id, claim_id=claim.id, embedding=[0.9, 0.9], model_name="test-model"
        )

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_claim_ids_without_vector_excludes_embedded_claims(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-3")
        embedded = await _make_claim(conn, user_id, source.id, "Embedded claim.")
        pending = await _make_claim(conn, user_id, source.id, "Pending claim.")
        repo = SemanticVectorRepository(conn)
        await repo.create(
            user_id=user_id, claim_id=embedded.id, embedding=[0.1], model_name="test-model"
        )

        missing = await repo.claim_ids_without_vector(source.id)

    assert missing == {pending.id}


@pytest.mark.asyncio
async def test_search_similar_ranks_by_cosine_distance(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-4")
        close = await _make_claim(conn, user_id, source.id, "Close claim.")
        far = await _make_claim(conn, user_id, source.id, "Far claim.")
        repo = SemanticVectorRepository(conn)
        await repo.create(
            user_id=user_id, claim_id=close.id, embedding=[1.0, 0.0], model_name="test-model"
        )
        await repo.create(
            user_id=user_id, claim_id=far.id, embedding=[0.0, 1.0], model_name="test-model"
        )

        results = await repo.search_similar([1.0, 0.0], limit=2)

    assert [r.claim.id for r in results] == [close.id, far.id]
    assert results[0].similarity > results[1].similarity
    assert results[0].similarity == pytest.approx(1.0, abs=1e-6)
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `MIGRATION_DATABASE_URL=... DATABASE_URL=... .venv/bin/pytest tests/kernel/test_semantic_vectors_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.db.semantic_vectors'`

- [ ] **Step 6: Implement `kernel/db/semantic_vectors.py`**

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Claim, SemanticVector, SimilarClaim

_COLUMNS = "id, user_id, claim_id, model_name, created_at, embedding::text AS embedding"

_CLAIM_COLUMNS = (
    "c.id, c.user_id, c.source_id, c.observation_id, c.claim_text, c.claim_type, "
    "c.confidence, c.extraction_method, c.model_name, c.prompt_version, c.status, "
    "c.created_at, c.metadata"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


def _embedding_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class SemanticVectorRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        claim_id: str | UUID,
        embedding: list[float],
        model_name: str,
    ) -> SemanticVector | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO semantic_vectors (user_id, claim_id, embedding, model_name)
                    VALUES (:user_id, :claim_id, CAST(:embedding AS vector), :model_name)
                    ON CONFLICT (claim_id) DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "claim_id": str(claim_id),
                    "embedding": _embedding_literal(embedding),
                    "model_name": model_name,
                },
            )
        ).mappings().first()
        return SemanticVector.from_row(_as_mapping(row)) if row else None

    async def get_for_claim(self, claim_id: str | UUID) -> SemanticVector | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM semantic_vectors WHERE claim_id = :claim_id"),
                {"claim_id": str(claim_id)},
            )
        ).mappings().first()
        return SemanticVector.from_row(_as_mapping(row)) if row else None

    async def claim_ids_without_vector(self, source_id: str | UUID) -> set[UUID]:
        rows = (
            await self.conn.execute(
                text(
                    "SELECT c.id FROM claims c "
                    "LEFT JOIN semantic_vectors sv ON sv.claim_id = c.id "
                    "WHERE c.source_id = :source_id AND sv.id IS NULL"
                ),
                {"source_id": str(source_id)},
            )
        ).all()
        return {row[0] for row in rows}

    async def search_similar(
        self, query_embedding: list[float], limit: int = 20
    ) -> list[SimilarClaim]:
        rows = (
            await self.conn.execute(
                text(
                    f"""
                    SELECT {_CLAIM_COLUMNS},
                           1 - (sv.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                    FROM semantic_vectors sv
                    JOIN claims c ON c.id = sv.claim_id
                    ORDER BY sv.embedding <=> CAST(:query_embedding AS vector) ASC
                    LIMIT :limit
                    """
                ),
                {"query_embedding": _embedding_literal(query_embedding), "limit": limit},
            )
        ).mappings().all()
        return [
            SimilarClaim(claim=Claim.from_row(_as_mapping(r)), similarity=float(r["similarity"]))
            for r in rows
        ]
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/test_semantic_vectors_repository.py -v`
Expected: 4 passed

- [ ] **Step 8: Add `list_for_source` to `ClaimRepository`**

In `kernel/db/claims.py`, add after `count_for_source` (keep the file's existing `_COLUMNS`/`_as_mapping` as-is):

```python
    async def list_for_source(self, source_id: str | UUID) -> list[Claim]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM claims WHERE source_id = :source_id "
                    "ORDER BY created_at"
                ),
                {"source_id": str(source_id)},
            )
        ).mappings().all()
        return [Claim.from_row(_as_mapping(r)) for r in rows]
```

- [ ] **Step 9: Write and run the `list_for_source` test**

Add to `tests/kernel/test_claims_repository.py`:

```python
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
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )

        result = await repo.list_for_source(source.id)

    assert len(result) == 3
```

Run: `.venv/bin/pytest tests/kernel/test_claims_repository.py -v`
Expected: all pass, including the new test.

- [ ] **Step 10: Add tenant isolation coverage**

Add to `tests/kernel/test_tenant_isolation.py`:

```python
@pytest.mark.asyncio
async def test_semantic_vectors_isolated_between_tenants(make_user):
    from kernel.db.semantic_vectors import SemanticVectorRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-vectors")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Secret vector source"}], src.id, user_a
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            observation_id=obs_id,
            claim_text="Secret claim for embedding.",
            claim_type="fact",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        vector = await SemanticVectorRepository(conn).create(
            user_id=user_a, claim_id=claim.id, embedding=[0.1, 0.2], model_name="test"
        )
        assert vector is not None

    async with session(user_b) as conn:
        assert await SemanticVectorRepository(conn).get_for_claim(claim.id) is None
        assert await SemanticVectorRepository(conn).search_similar([0.1, 0.2]) == []
```

Run: `.venv/bin/pytest tests/kernel/test_tenant_isolation.py -v`
Expected: all pass.

- [ ] **Step 11: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 12: Commit**

```bash
git add migrations/versions/0007_semantic_vectors.py kernel/models.py kernel/db/semantic_vectors.py kernel/db/claims.py tests/kernel/test_semantic_vectors_repository.py tests/kernel/test_claims_repository.py tests/kernel/test_tenant_isolation.py
git commit -m "feat: add semantic_vectors table, model, and repository for claim embeddings"
```

---

### Task 2: Embedding provider and worker

**Files:**
- Create: `worker/tasks/errors.py`
- Modify: `worker/tasks/extract_claims.py` (use shared error redaction; auto-enqueue `embed_claims`)
- Create: `kernel/ai/embeddings.py`
- Create: `worker/tasks/embed_claims.py`
- Modify: `worker/main.py` (register the new actor)
- Create: `tests/kernel/test_embeddings.py`
- Create: `tests/worker/test_embed_claims.py`
- Modify: `tests/worker/test_extract_claims.py` (auto-enqueue coverage)

**Interfaces:**
- Consumes: Task 1's `SemanticVectorRepository`, `ClaimRepository.list_for_source`.
- Produces: `worker/tasks/errors.py`'s `public_error(message: str) -> str`; `kernel/ai/embeddings.py`'s `EmbeddingSettings.from_env()`, `OpenAIEmbedder.embed(texts) -> list[list[float]]`, `get_embedder(settings=None) -> OpenAIEmbedder`; `worker/tasks/embed_claims.py`'s `embed_claims` dramatiq actor (`source_id, user_id, job_id`) and `heal_embed_claims`.

**Why `worker/tasks/errors.py` first:** `extract_claims.py` needs to enqueue `embed_claims` (a one-directional import: extract → embed). `embed_claims.py` needs the same API-key redaction `extract_claims.py` already has as `_public_error`. Importing `_public_error` back from `extract_claims.py` into `embed_claims.py` would create a circular import. Extracting it into a small shared module breaks the cycle without duplicating the regex.

- [ ] **Step 1: Extract the shared error redaction helper**

Create `worker/tasks/errors.py`:

```python
from __future__ import annotations

import re


def public_error(message: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_*\\-]+", "sk-REDACTED", message)
    if "Incorrect API key provided" in redacted:
        return "OpenAI rejected the configured API key"
    return redacted
```

In `worker/tasks/extract_claims.py`, replace the local definition:

```python
def _public_error(message: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_*\\-]+", "sk-REDACTED", message)
    if "Incorrect API key provided" in redacted:
        return "OpenAI rejected the configured API key"
    return redacted
```

with:

```python
from worker.tasks.errors import public_error as _public_error
```

placed in the import block (remove the now-unused `import re` if nothing else in the file uses it — check with `grep -n "re\." worker/tasks/extract_claims.py` first; the batching/regex logic elsewhere doesn't use `re`, so `import re` should be removed).

- [ ] **Step 2: Verify existing tests still pass**

Run: `.venv/bin/pytest tests/worker/test_extract_claims.py -v -k public_error`
Expected: `test_public_error_redacts_openai_api_key_fragments` passes unchanged (same name, same behavior, now delegating to the shared module).

- [ ] **Step 3: Write the failing settings/provider test**

Create `tests/kernel/test_embeddings.py`:

```python
import pytest

from kernel.ai.embeddings import EmbeddingSettings, OpenAIEmbedder, get_embedder


def test_embedding_settings_from_env_reads_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("EMBEDDING_AUTORUN", raising=False)
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)

    settings = EmbeddingSettings.from_env()

    assert settings.openai_embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536
    assert settings.embedding_autorun is False
    assert settings.embedding_batch_size == 100


def test_embedding_settings_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "custom-model")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "256")
    monkeypatch.setenv("EMBEDDING_AUTORUN", "true")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "50")

    settings = EmbeddingSettings.from_env()

    assert settings.openai_embedding_model == "custom-model"
    assert settings.embedding_dimensions == 256
    assert settings.embedding_autorun is True
    assert settings.embedding_batch_size == 50


def test_get_embedder_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "openai")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_embedder()


def test_get_embedder_raises_for_unsupported_provider(monkeypatch):
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "anthropic")

    with pytest.raises(ValueError, match="unsupported ACTIVE_AI_PROVIDER"):
        get_embedder()


@pytest.mark.asyncio
async def test_openai_embedder_returns_empty_list_for_empty_input():
    embedder = OpenAIEmbedder(api_key="sk-fake", model="text-embedding-3-small", dimensions=1536)
    result = await embedder.embed([])
    assert result == []
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.ai.embeddings'`

- [ ] **Step 5: Implement `kernel/ai/embeddings.py`**

```python
from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_embedding_model: str
    embedding_dimensions: int
    embedding_autorun: bool
    embedding_batch_size: int

    @classmethod
    def from_env(cls) -> EmbeddingSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_embedding_model=os.environ.get(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            embedding_dimensions=max(1, int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))),
            embedding_autorun=os.environ.get("EMBEDDING_AUTORUN", "false").lower() == "true",
            embedding_batch_size=max(1, int(os.environ.get("EMBEDDING_BATCH_SIZE", "100"))),
        )


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self.dimensions
        )
        return [item.embedding for item in response.data]


def get_embedder(settings: EmbeddingSettings | None = None) -> OpenAIEmbedder:
    settings = settings or EmbeddingSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIEmbedder(
        settings.openai_api_key, settings.openai_embedding_model, settings.embedding_dimensions
    )
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/test_embeddings.py -v`
Expected: 5 passed

- [ ] **Step 7: Write the failing worker test**

Create `tests/worker/test_embed_claims.py`:

```python
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


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        self.calls.append(list(texts))
        return [[float(len(t)), 0.0] for t in texts]


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
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/worker/test_embed_claims.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.tasks.embed_claims'`

- [ ] **Step 9: Implement `worker/tasks/embed_claims.py`**

```python
from __future__ import annotations

from itertools import batched
from typing import Any

import dramatiq

from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.claims import ClaimRepository
from kernel.db.jobs import JobRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

get_broker()


async def _embed_claims(source_id: str, user_id: str, job_id: str) -> None:
    settings = EmbeddingSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        vector_repo = SemanticVectorRepository(conn)
        pending_ids = await vector_repo.claim_ids_without_vector(source_id)
        if not pending_ids:
            await JobRepository(conn).mark_completed(job_id, result={"embedded": 0})
            return
        all_claims = await ClaimRepository(conn).list_for_source(source_id)
        pending_claims = [c for c in all_claims if c.id in pending_ids]

    async with session(user_id) as conn:
        await JobRepository(conn).update_progress(
            job_id, items_completed=0, items_total=len(pending_claims)
        )

    try:
        embedder = get_embedder(settings)
        embedded_count = 0
        processed_count = 0
        for batch in batched(pending_claims, settings.embedding_batch_size):
            vectors = await embedder.embed([c.claim_text for c in batch])
            async with session(user_id) as conn:
                vector_repo = SemanticVectorRepository(conn)
                for claim, vector in zip(batch, vectors, strict=True):
                    created = await vector_repo.create(
                        user_id=user_id,
                        claim_id=claim.id,
                        embedding=vector,
                        model_name=settings.openai_embedding_model,
                    )
                    if created is not None:
                        embedded_count += 1
                processed_count += len(batch)
                await JobRepository(conn).update_progress(
                    job_id, items_completed=processed_count, items_total=len(pending_claims)
                )

        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id, result={"embedded": embedded_count}
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


# Embedding a batch is one cheap OpenAI call (no per-item reasoning like claim
# extraction) — an hour comfortably covers even a large source's worth of
# batches without needing extraction's 3-hour ceiling.
EMBED_CLAIMS_TIME_LIMIT_MS = 60 * 60 * 1000


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_embed_claims",
    time_limit=EMBED_CLAIMS_TIME_LIMIT_MS,
)
def embed_claims(source_id: str, user_id: str, job_id: str) -> None:
    run_actor(_embed_claims(source_id, user_id, job_id))


async def _heal_embed_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    source_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "embed_claims", payload={"source_id": source_id}
        )
    embed_claims.send_with_options(
        args=(source_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_embed_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_embed_claims(original_message, stats))
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/worker/test_embed_claims.py -v`
Expected: 6 passed

- [ ] **Step 11: Register the actor in `worker/main.py`**

Change:

```python
from worker.tasks import extract_claims, ingest_source  # noqa: E402,F401  (registers actors)
```

to:

```python
from worker.tasks import embed_claims, extract_claims, ingest_source  # noqa: E402,F401  (registers actors)
```

- [ ] **Step 12: Write the failing auto-enqueue test**

Add to `tests/worker/test_extract_claims.py` (after `test_extract_claims_auto_promotes_candidates_to_concepts`):

```python
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
```

- [ ] **Step 13: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/worker/test_extract_claims.py -v -k auto_enqueues_embedding`
Expected: FAIL — `worker.tasks.extract_claims` has no attribute `embed_claims`.

- [ ] **Step 14: Wire the auto-enqueue into `_extract_claims`**

In `worker/tasks/extract_claims.py`, add the import:

```python
from kernel.ai.embeddings import EmbeddingSettings
from worker.tasks.embed_claims import embed_claims
```

Replace the success block at the end of the `try:` in `_extract_claims`:

```python
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id,
                result={
                    "claims": claim_count,
                    "concept_candidates": candidate_count,
                    "processed_observations": len(pending_observations),
                    "skipped_observations": len(all_observations) - len(pending_observations),
                },
            )
```

with:

```python
        embed_job_id = None
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id,
                result={
                    "claims": claim_count,
                    "concept_candidates": candidate_count,
                    "processed_observations": len(pending_observations),
                    "skipped_observations": len(all_observations) - len(pending_observations),
                },
            )
            # Auto-enqueue embedding for this chunk's claims. Sibling chunks
            # for the same source may fire this too — claim_ids_without_vector
            # makes each embed_claims run a no-op once nothing is pending, so
            # redundant triggers are harmless rather than duplicating work.
            if claim_count > 0 and EmbeddingSettings.from_env().embedding_autorun:
                embed_job = await JobRepository(conn).create(
                    user_id, "embed_claims", payload={"source_id": source_id}
                )
                embed_job_id = embed_job.id
        if embed_job_id is not None:
            embed_claims.send(source_id, user_id, str(embed_job_id))
```

- [ ] **Step 15: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/worker/test_extract_claims.py -v`
Expected: all pass (including the two new auto-enqueue tests).

- [ ] **Step 16: Run the full backend/kernel/worker suite, lint, and type-check**

Run: `.venv/bin/pytest tests/ -q && .venv/bin/ruff check kernel backend worker tests && .venv/bin/mypy kernel backend worker`
Expected: all pass, no lint/type errors.

- [ ] **Step 17: Commit**

```bash
git add worker/tasks/errors.py worker/tasks/extract_claims.py kernel/ai/embeddings.py worker/tasks/embed_claims.py worker/main.py tests/kernel/test_embeddings.py tests/worker/test_embed_claims.py tests/worker/test_extract_claims.py
git commit -m "feat: add embed_claims worker task, auto-enqueued after claim extraction"
```

---

### Task 3: API — embed-claims endpoint and semantic search

**Files:**
- Modify: `backend/app/api/sources.py` (add `POST /sources/{source_id}/embed-claims`)
- Create: `backend/app/api/search.py` (add `GET /search`)
- Modify: `backend/app/main.py` (register the new router)
- Modify: `tests/backend/test_sources_api.py` (embed-claims endpoint tests)
- Create: `tests/backend/test_search_api.py`

**Interfaces:**
- Consumes: Task 2's `embed_claims` actor; Task 1's `SemanticVectorRepository.search_similar`; `kernel.ai.embeddings.get_embedder`/`EmbeddingSettings`.
- Produces: `POST /sources/{source_id}/embed-claims` → `{"job_id": str, "status": "pending"}`; `GET /search?q=...&limit=20` → `list[{...claim fields..., "similarity": float}]`.

- [ ] **Step 1: Write the failing embed-claims endpoint test**

Add to `tests/backend/test_sources_api.py` (near the existing `test_manual_claim_extraction_*` tests):

```python
@pytest.fixture
def _no_embedding_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.sources.embed_claims.send",
        lambda *a, **k: calls.append(a),
    )
    return calls


@pytest.mark.asyncio
async def test_manual_embed_claims_creates_job(client, seeded_user, _no_embedding_broker):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "manual-embed")
        await SourceRepository(conn).mark_verified(source.id)

    await _login(client)
    r = await client.post(f"/sources/{source.id}/embed-claims")

    assert r.status_code == 202
    assert "job_id" in r.json()
    assert len(_no_embedding_broker) == 1

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_manual_embed_claims_rejects_unverified_source(client, seeded_user, _no_embedding_broker):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "embed-unverified")

    await _login(client)
    r = await client.post(f"/sources/{source.id}/embed-claims")

    assert r.status_code == 409
    assert _no_embedding_broker == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_manual_embed_claims_unknown_source_returns_404(client, seeded_user, _no_embedding_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post("/sources/00000000-0000-0000-0000-000000000000/embed-claims")
    assert r.status_code == 404
    assert _no_embedding_broker == []
```

Note: `await _login(client)` in these three tests needs the module's existing `_login` helper — already defined at the top of `tests/backend/test_sources_api.py`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/backend/test_sources_api.py -v -k embed_claims`
Expected: FAIL — 404 on all three (route doesn't exist yet).

- [ ] **Step 3: Implement the endpoint in `backend/app/api/sources.py`**

Add the import:

```python
from worker.tasks.embed_claims import embed_claims
```

Add after `extract_source_claims`:

```python
@router.post("/sources/{source_id}/embed-claims", status_code=202)
async def embed_source_claims(
    source_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        source = await SourceRepository(conn).get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="not found")
        if source.import_status != "VERIFIED":
            raise HTTPException(status_code=409, detail="source is not verified")
        job = await JobRepository(conn).create(
            user_id, "embed_claims", payload={"source_id": source_id}
        )
    embed_claims.send(source_id, user_id, str(job.id))
    return {"job_id": str(job.id), "status": "pending"}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/backend/test_sources_api.py -v -k embed_claims`
Expected: 3 passed

- [ ] **Step 5: Write the failing search endpoint test**

Create `tests/backend/test_search_api.py`:

```python
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
        await vector_repo.create(
            user_id=seeded_user, claim_id=close_claim.id, embedding=[1.0, 0.0], model_name="test"
        )
        await vector_repo.create(
            user_id=seeded_user, claim_id=far_claim.id, embedding=[0.0, 1.0], model_name="test"
        )

    fixed = _FixedEmbedder({"query": [1.0, 0.0]}, default=[0.0, 0.0])
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
        await SemanticVectorRepository(conn).create(
            user_id=other_user, claim_id=claim.id, embedding=[1.0, 0.0], model_name="test"
        )

    fixed = _FixedEmbedder({"query": [1.0, 0.0]}, default=[0.0, 0.0])
    monkeypatch.setattr("backend.app.api.search.get_embedder", lambda settings: fixed)

    await _login(client)
    r = await client.get("/search", params={"q": "query"})

    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_search_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/search", params={"q": "anything"})
    assert r.status_code == 401
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/backend/test_search_api.py -v`
Expected: FAIL with 404 (no `/search` route registered yet).

- [ ] **Step 7: Implement `backend/app/api/search.py`**

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.api.concepts import serialize_claim
from backend.app.auth.dependencies import get_current_user
from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session

router = APIRouter()


@router.get("/search")
async def search_claims(
    q: str,
    limit: int = 20,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    embedder = get_embedder(EmbeddingSettings.from_env())
    [query_embedding] = await embedder.embed([q])
    async with session(user_id) as conn:
        results = await SemanticVectorRepository(conn).search_similar(query_embedding, limit=limit)
    return [{**serialize_claim(r.claim), "similarity": r.similarity} for r in results]
```

- [ ] **Step 8: Register the router in `backend/app/main.py`**

Change:

```python
from backend.app.api import auth, claims, concepts, dashboard, jobs, observations, sources
```

to:

```python
from backend.app.api import auth, claims, concepts, dashboard, jobs, observations, search, sources
```

and add after `app.include_router(concepts.router)`:

```python
    app.include_router(search.router)
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/backend/test_search_api.py -v`
Expected: 3 passed

- [ ] **Step 10: Run the full backend suite, lint, and type-check**

Run: `.venv/bin/pytest tests/ -q && .venv/bin/ruff check backend tests && .venv/bin/mypy backend`
Expected: all pass, no errors.

- [ ] **Step 11: Commit**

```bash
git add backend/app/api/sources.py backend/app/api/search.py backend/app/main.py tests/backend/test_sources_api.py tests/backend/test_search_api.py
git commit -m "feat: add embed-claims endpoint and semantic search API"
```

---

### Task 4: Frontend — search page and embed control

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `SearchResult`)
- Modify: `frontend/src/lib/api.ts` (add `search`, `embedClaims`)
- Modify: `frontend/src/components/layout/NavIcon.tsx` (add `search` icon)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (add Search nav item)
- Create: `frontend/src/app/(app)/search/page.tsx`
- Create: `frontend/src/app/(app)/search/search.test.tsx`
- Modify: `frontend/src/lib/api.test.ts` (cover the two new client functions)

**Interfaces:**
- Consumes: Task 3's `GET /search`, `POST /sources/{source_id}/embed-claims`.
- Produces: `search(query, limit?) -> Promise<SearchResult[]>`, `embedClaims(sourceId) -> Promise<{jobId, status}>`; `/search` route.

- [ ] **Step 1: Add `SearchResult` to `frontend/src/lib/types.ts`**

Add after the `Claim` interface:

```typescript
export interface SearchResult extends Claim {
  similarity: number
}
```

- [ ] **Step 2: Write the failing api.test.ts cases**

Add to `frontend/src/lib/api.test.ts` (extend the existing import line and add two tests at the end):

```typescript
import { ApiError, embedClaims, getSource, listObservations, listSources, login, me, search, uploadSource } from "./api"
```

```typescript
test("search sends q and limit as query params and maps similarity", async () => {
  const f = mockFetch(200, [
    { id: "c1", source_id: "s1", observation_id: "o1", claim_text: "hi", claim_type: "fact", confidence: 0.9, extraction_method: "test", model_name: null, prompt_version: null, status: "proposed", created_at: "2024-01-01T00:00:00Z", similarity: 0.87 },
  ])
  vi.stubGlobal("fetch", f)
  const [result] = await search("hello", 5)
  expect(result.similarity).toBe(0.87)
  expect(result.claimText).toBe("hi")
  const [url] = f.mock.calls[0]
  expect(url).toContain("/api/search?")
  expect(url).toContain("q=hello")
  expect(url).toContain("limit=5")
})

test("embedClaims posts to /sources/:id/embed-claims and returns jobId/status", async () => {
  const f = mockFetch(200, { job_id: "j1", status: "pending" })
  vi.stubGlobal("fetch", f)
  const result = await embedClaims("s1")
  expect(result).toEqual({ jobId: "j1", status: "pending" })
  const [url, init] = f.mock.calls[0]
  expect(url).toBe("/api/sources/s1/embed-claims")
  expect(init.method).toBe("POST")
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL — `search`/`embedClaims` are not exported from `./api`.

- [ ] **Step 4: Implement `search` and `embedClaims` in `frontend/src/lib/api.ts`**

Add after `getConceptClaims`:

```typescript
export async function search(query: string, limit = 20): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const r = await req(`/search?${params.toString()}`)
  if (!r.ok) throw await readError(r, "search failed")
  const rows = (await r.json()) as Record<string, unknown>[]
  return rows.map((d) => ({ ...toClaim(d), similarity: Number(d.similarity) }))
}

export async function embedClaims(sourceId: string): Promise<{ jobId: string; status: string }> {
  const r = await req(`/sources/${sourceId}/embed-claims`, { method: "POST" })
  if (!r.ok) throw await readError(r, "embedClaims failed")
  const d = await r.json()
  return { jobId: d.job_id, status: d.status }
}
```

Add `SearchResult` to the type-only import at the top of the file:

```typescript
import type {
  Claim,
  Concept,
  ConceptCandidate,
  DashboardSummary,
  Job,
  Observation,
  SearchResult,
  Source,
  SourceType,
} from "./types"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: all pass.

- [ ] **Step 6: Add the search icon**

In `frontend/src/components/layout/NavIcon.tsx`, add `"search"` to the `IconName` union:

```typescript
export type IconName =
  | "dashboard"
  | "inventory_2"
  | "database"
  | "visibility"
  | "analytics"
  | "hub"
  | "search"
  | "toggle_off"
  | "toggle_on"
```

Add to the `ICONS` record (any position; grouped near `visibility` for readability):

```typescript
  search: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
```

- [ ] **Step 7: Add the Search nav item**

In `frontend/src/components/layout/Sidebar.tsx`, add to `NAV_ITEMS` after `Concepts`:

```typescript
  { label: "Search", href: "/search", icon: "search" },
```

- [ ] **Step 8: Write the failing search page test**

Create `frontend/src/app/(app)/search/search.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import type { SearchResult } from "@/lib/types"
import SearchPage from "./page"

vi.mock("@/lib/api", () => ({
  search: vi.fn(),
}))

import { search } from "@/lib/api"
const mockSearch = vi.mocked(search)

const MOCK_RESULTS: SearchResult[] = [
  {
    id: "c1",
    sourceId: "s1",
    observationId: "o1",
    claimText: "The user prefers dark mode.",
    claimType: "preference",
    confidence: 0.9,
    extractionMethod: "test",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-01-01T00:00:00Z",
    similarity: 0.92,
  },
]

function renderPage() {
  return render(<SearchPage />)
}

describe("SearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows page title Search", () => {
    renderPage()
    expect(screen.getByText("Search")).toBeInTheDocument()
  })

  it("runs a search on submit and renders results with similarity", async () => {
    mockSearch.mockResolvedValueOnce(MOCK_RESULTS)
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "dark mode")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText("The user prefers dark mode.")).toBeInTheDocument()
      expect(screen.getByText("92% match")).toBeInTheDocument()
    })
    expect(mockSearch).toHaveBeenCalledWith("dark mode")
  })

  it("shows empty state when no results match", async () => {
    mockSearch.mockResolvedValueOnce([])
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "nothing")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText("No matching claims found.")).toBeInTheDocument()
    })
  })

  it("shows inline error when search throws", async () => {
    mockSearch.mockRejectedValueOnce(new Error("search failed"))
    renderPage()

    await userEvent.type(screen.getByLabelText("Search claims"), "x")
    await userEvent.click(screen.getByRole("button", { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 9: Run the test to verify it fails**

Run: `cd frontend && npx vitest run "src/app/(app)/search/search.test.tsx"`
Expected: FAIL — `./page` module not found.

- [ ] **Step 10: Implement `frontend/src/app/(app)/search/page.tsx`**

```tsx
"use client"

import { useState } from "react"
import { search } from "@/lib/api"
import type { SearchResult } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"

export default function SearchPage() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await search(query.trim())
      setResults(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6 p-8">
      <h1 className="font-heading text-2xl font-medium text-ink">Search</h1>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          aria-label="Search claims"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search claims by meaning…"
          value={query}
        />
        <button
          className="rounded-meridian bg-ember px-4 py-2 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={loading || !query.trim()}
          type="submit"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      {results !== null && (
        <div className="divide-y divide-hairline border-y border-hairline">
          {results.map((result) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px_120px]" key={result.id}>
              <p className="text-sm leading-6 text-ink">{result.claimText}</p>
              <div>
                <Badge className="font-mono uppercase">{result.claimType}</Badge>
              </div>
              <div className="font-mono text-xs text-muted">
                {Math.round(result.similarity * 100)}% match
              </div>
            </article>
          ))}
          {results.length === 0 && (
            <p className="py-8 text-sm text-muted">No matching claims found.</p>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `cd frontend && npx vitest run "src/app/(app)/search/search.test.tsx"`
Expected: 4 passed

- [ ] **Step 12: Write the failing SourceRow test for the Embed button**

Add to `frontend/src/components/domain/SourceRow.test.tsx`:

```typescript
describe("SourceRow embed button", () => {
  it("is disabled when the source has no claims yet", () => {
    renderRow({ onEmbed: () => {} })
    expect(screen.getByRole("button", { name: "Embed" })).toBeDisabled()
  })

  it("is enabled once claims exist and calls onEmbed with the source on click", async () => {
    const onEmbed = vi.fn()
    renderRow({ source: { ...SOURCE, claimCount: 3 }, onEmbed })

    const button = screen.getByRole("button", { name: "Embed" })
    expect(button).not.toBeDisabled()
    await userEvent.click(button)

    expect(onEmbed).toHaveBeenCalledWith(expect.objectContaining({ id: SOURCE.id }))
  })

  it("shows Embedding and disables the button while isEmbedding is true", () => {
    renderRow({ source: { ...SOURCE, claimCount: 3 }, onEmbed: () => {}, isEmbedding: true })
    expect(screen.getByRole("button", { name: "Embedding" })).toBeDisabled()
  })

  it("does not render the embed button when onEmbed is not provided", () => {
    renderRow()
    expect(screen.queryByRole("button", { name: /embed/i })).not.toBeInTheDocument()
  })
})
```

Add the two missing imports at the top of the file:

```typescript
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
```

(replace the existing `import { describe, expect, it } from "vitest"` with the `vi`-including version above).

- [ ] **Step 13: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/domain/SourceRow.test.tsx`
Expected: FAIL — no button named "Embed" exists yet.

- [ ] **Step 14: Add the Embed button to `SourceRow.tsx`**

Change the props interface and destructuring:

```typescript
interface SourceRowProps {
  source: Source
  isExtracting?: boolean
  isEmbedding?: boolean
  itemsCompleted?: number | null
  itemsTotal?: number | null
  onExtract?: (source: Source) => void
  onEmbed?: (source: Source) => void
  onDelete?: (source: Source) => void
}

export function SourceRow({
  source,
  isExtracting = false,
  isEmbedding = false,
  itemsCompleted = null,
  itemsTotal = null,
  onExtract,
  onEmbed,
  onDelete,
}: SourceRowProps) {
  const isPurged = source.importStatus === "PURGED"
  const filenameClass = isPurged
    ? "font-heading text-muted line-through"
    : "font-heading text-ink"
  const canExtract = source.importStatus === "VERIFIED" && onExtract !== undefined
  const canEmbed =
    source.importStatus === "VERIFIED" && source.claimCount > 0 && onEmbed !== undefined
  const canDelete = source.claimCount === 0 && !isPurged
  const showProgress = isExtracting && Boolean(itemsTotal)
```

Add the button in the actions cell, between the Extract/Retry button and the Delete button:

```tsx
        {onEmbed !== undefined && (
          <Button
            className="ml-2 px-3 py-1.5 font-mono text-[11px] uppercase"
            disabled={!canEmbed || isEmbedding}
            onClick={() => onEmbed(source)}
            type="button"
            variant="ghost"
          >
            {isEmbedding ? "Embedding" : "Embed"}
          </Button>
        )}
```

- [ ] **Step 15: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/domain/SourceRow.test.tsx`
Expected: all pass (7 total: 3 existing progress-bar tests + 4 new embed-button tests).

- [ ] **Step 16: Wire the Embed button into `frontend/src/app/(app)/sources/page.tsx`**

Add the import:

```typescript
import { embedClaims, extractClaims, getJob, listSources, purgeSource } from "@/lib/api"
```

Add state after the existing `running` state:

```typescript
const [embedding, setEmbedding] = useState<Record<string, boolean>>({})
```

Add a handler after `startExtraction`:

```typescript
async function startEmbedding(source: Source) {
  setError(null)
  setEmbedding((current) => ({ ...current, [source.id]: true }))
  try {
    await embedClaims(source.id)
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : "Claim embedding failed")
  } finally {
    setEmbedding((current) => ({ ...current, [source.id]: false }))
  }
}
```

Pass the new props to `<SourceRow>`:

```tsx
              <SourceRow
                isEmbedding={Boolean(embedding[source.id])}
                isExtracting={Boolean(running[source.id])}
                itemsCompleted={running[source.id]?.itemsCompleted ?? null}
                itemsTotal={running[source.id]?.itemsTotal ?? null}
                key={source.id}
                onDelete={deleteSource}
                onEmbed={startEmbedding}
                onExtract={startExtraction}
                source={source}
              />
```

- [ ] **Step 17: Run the sources page test suite to confirm nothing broke**

Run: `cd frontend && npx vitest run "src/app/(app)/sources/sources.test.tsx" src/components/domain/SourceRow.test.tsx`
Expected: all pass.

- [ ] **Step 18: Run the full frontend suite, typecheck, and lint**

Run: `cd frontend && npm test -- --run && npx tsc --noEmit && npx eslint src`
Expected: all pass, no errors.

- [ ] **Step 19: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/components/layout/NavIcon.tsx frontend/src/components/layout/Sidebar.tsx "frontend/src/app/(app)/search/page.tsx" "frontend/src/app/(app)/search/search.test.tsx" frontend/src/components/domain/SourceRow.tsx frontend/src/components/domain/SourceRow.test.tsx
git commit -m "feat: add semantic search page and embed-claims control"
```

---

### Task 5: Docs, env, and final review

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docker-compose.yml` (env passthrough for backend/worker)

**Interfaces:** None — documentation and configuration only.

- [ ] **Step 1: Add embedding env vars to `.env.example`**

In the `# AI (Plan/Phase 1+)` section, after `CLAIM_EXTRACTION_BATCH_SIZE=12`:

```
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_AUTORUN=false
EMBEDDING_BATCH_SIZE=100
```

- [ ] **Step 2: Pass the new env vars through in `docker-compose.yml`**

In both the `backend` and `worker` services' `environment:` blocks, add after `CLAIM_EXTRACTION_BATCH_SIZE`:

```yaml
      OPENAI_EMBEDDING_MODEL: ${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}
      EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-1536}
      EMBEDDING_AUTORUN: ${EMBEDDING_AUTORUN:-false}
      EMBEDDING_BATCH_SIZE: ${EMBEDDING_BATCH_SIZE:-100}
```

- [ ] **Step 3: Add a README section**

In `README.md`, insert after the "Phase 1 Concept Promotion" section (before "## Project Layout"):

```markdown
## Phase 1 Embeddings & Semantic Search

Claims are embedded via OpenAI (`text-embedding-3-small` by default) into a
pgvector-backed `semantic_vectors` table (HNSW cosine index), one row per
claim:

- automatic `embed_claims` jobs after each extraction chunk persists claims,
  when `EMBEDDING_AUTORUN=true`
- manual `POST /api/sources/{source_id}/embed-claims`

`GET /api/search?q=...&limit=20` embeds the query and ranks claims by cosine
similarity, scoped by RLS like every other query. Concept embeddings, hybrid
keyword+semantic search, and re-ranking are out of scope for this plan — see
the Planetarium (Phase 4), which consumes these embeddings for its spatial
projection layer.

---
```

Update the "Phase 1 Claim Extraction" section's closing line — change:

```
Claim and concept-candidate rows are tenant-scoped by PostgreSQL RLS. Concept
candidates are proposed memory only; canonical concepts, graph edges,
contradiction detection, embeddings, Custodian, and Planetarium work remain
out of scope for Phase 1 Plan 1.
```

to:

```
Claim and concept-candidate rows are tenant-scoped by PostgreSQL RLS. Concept
candidates are proposed memory only; canonical concepts, graph edges,
contradiction detection, Custodian, and Planetarium work remain out of scope
for Phase 1 Plan 1 (embeddings are covered in Phase 1 Plan 3).
```

- [ ] **Step 4: Run every gate one final time**

Run:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
export DATABASE_URL="postgresql+asyncpg://locigraph_app:changeme@localhost:5432/locigraph"
export APP_DB_PASSWORD="changeme"
export LOCIGRAPH_EMAIL="you@example.com"
export LOCIGRAPH_PASSWORD="changeme"
export JWT_SECRET="changeme-generate-with-openssl-rand-hex-32"
export RAW_STORAGE_PATH="/tmp/locigraph-raw"
.venv/bin/pytest -q tests/
.venv/bin/ruff check kernel backend worker tests
.venv/bin/mypy kernel backend worker
cd frontend && npm test -- --run && npx tsc --noEmit && npx eslint src
```
Expected: everything green.

- [ ] **Step 5: Browser QA**

Start the stack (`docker compose up -d`, rebuilding backend/worker/frontend), log in, and verify:
- `POST /sources/{id}/embed-claims` on a verified source with claims completes and creates `semantic_vectors` rows (check via `docker exec` psql or by re-running search).
- `/search` returns a ranked result for a query semantically close to a seeded claim, and an empty state for a query matching nothing.
- A second user never sees the first user's claims in `/search` results.

- [ ] **Step 6: Commit**

```bash
git add .env.example README.md docker-compose.yml
git commit -m "docs: document embeddings + semantic search, add env vars"
```

Do not push or open a PR — that decision belongs to the user, same as this project's established convention for prior plans.

## Out of Scope (carried over from the original Plan 3 draft)

- Concept embeddings — only claims are embedded in this plan.
- Hybrid keyword+semantic search, query rewriting, or re-ranking beyond raw cosine similarity.
- Re-embedding on claim edit or versioning (claims are currently immutable once created).
- Contradiction detection, Custodian, and the Planetarium's physics/projection/rendering layers — this plan only produces the embeddings those later phases will consume.
- Multi-provider embeddings beyond the OpenAI implementation.
- Chunking `embed_claims` the way `extract_claims` was chunked this session — claim volumes embedding in a single job are new (no prior reliability incident to fix), and `claim_ids_without_vector` already makes retries/heals resumable. Revisit if a source's claim count makes a single embedding job impractically slow.
