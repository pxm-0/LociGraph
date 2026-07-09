# Custodian Core (Phase 3 Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Custodian's conversational core — chat sessions, streamed LLM replies, and read-only retrieval over the user's claims and concepts via LLM tool-calling.

**Architecture:** `custodian_sessions`/`custodian_messages` tables (RLS-scoped like every other table) persist conversations. `kernel/ai/custodian.py` wraps OpenAI's Responses API in streaming mode with two function tools (`search_archive` over claim embeddings, `search_concepts` over concept names + revision history), looping on tool calls until the model produces a final answer. `backend/app/api/custodian.py` exposes session CRUD plus a `text/event-stream` endpoint that generates the reply in a detached background task (so a client disconnect doesn't cut generation short) and forwards tokens through a queue. The frontend adds a floating `Orb` component (rendered in `AppChrome`) that expands into a chat panel.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries), asyncpg, Postgres 16, OpenAI Python SDK 2.x Responses API (streaming + function tools), Next.js/React/TypeScript, pytest + vitest.

## Global Constraints

- The next migration revision is `0011` (heads: `0001`→...→`0009`→`0010`).
- No DB `CHECK` constraints — `role` on `custodian_messages` is validated in Python, matching every other enum-like column in this codebase (`claim_type`, `assertion_type`, `classification`).
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod, matching every existing model in `kernel/models.py`.
- All repository methods take an already-open `AsyncConnection` via `BaseRepository.__init__`; RLS scoping happens implicitly through `kernel/db/session.py`'s `session(user_id)` context manager.
- `ACTIVE_AI_PROVIDER` gates every AI call the same way (`if settings.active_ai_provider != "openai": raise ValueError(...)`) — this plan follows that exact convention a fifth time (after `claim_extraction`, `embeddings`, `contradiction_detection`, `revision_synthesis`), not a shared factory (the codebase has never extracted one despite four prior repetitions — follow established style, don't unilaterally restructure).
- Design reference: `docs/superpowers/specs/2026-07-09-custodian-core-design.md`.
- Unlike every other AI call in this codebase, the Custodian is not a dramatiq job — it's called directly from the FastAPI backend, since chat needs sub-second turnaround, not a queue+poll cycle. This is this codebase's first streaming (SSE) endpoint and its first fire-and-forget background `asyncio.Task`.

---

### Task 1: Migration, models, and CustodianRepository

**Files:**
- Create: `migrations/versions/0011_custodian.py`
- Modify: `kernel/models.py` (add `CustodianSession`, `CustodianMessage`)
- Create: `kernel/db/custodian.py`
- Create: `tests/kernel/test_custodian_repository.py`
- Modify: `tests/kernel/test_tenant_isolation.py` (add a Custodian isolation case)
- Modify: `tests/conftest.py` (add `custodian_messages`/`custodian_sessions` to the `make_user` teardown)
- Modify: `tests/backend/conftest.py` (same, for `seeded_user`'s two cleanup blocks)

**Interfaces:**
- Produces: `CustodianSession` dataclass (`id, user_id, title, started_at, ended_at, model, provider`); `CustodianMessage` dataclass (`id, session_id, user_id, role, content, tool_name, tool_input, tool_output, created_at`); `CustodianRepository(conn)` with `create_session(*, user_id, model, provider, title=None) -> CustodianSession`, `get_session(session_id) -> CustodianSession | None`, `list_sessions(*, limit=50, offset=0) -> list[CustodianSession]`, `end_session(session_id) -> CustodianSession | None`, `set_title(session_id, title) -> None`, `add_message(*, session_id, user_id, role, content, tool_name=None, tool_input=None, tool_output=None) -> CustodianMessage`, `list_messages(session_id) -> list[CustodianMessage]`, `count_messages(session_id) -> int`.
- Consumes: `kernel/db/base_repository.py`'s `BaseRepository`/`strip_nul_bytes`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0011_custodian.py`:

```python
"""custodian — chat sessions and messages

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-09
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

DATA_TABLES = ["custodian_sessions", "custodian_messages"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custodian_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            title TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at TIMESTAMPTZ,
            model TEXT NOT NULL,
            provider TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE custodian_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES custodian_sessions(id),
            user_id UUID NOT NULL REFERENCES users(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tool_name TEXT,
            tool_input TEXT,
            tool_output TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX custodian_sessions_user_idx ON custodian_sessions (user_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX custodian_messages_session_idx ON custodian_messages (session_id, created_at)"
    )
    for table in DATA_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO locigraph_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS custodian_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS custodian_sessions CASCADE")
```

- [ ] **Step 2: Run the migration**

Run: `alembic upgrade head`
Expected: no errors; `alembic current` shows `0011`.

- [ ] **Step 3: Add the models**

In `kernel/models.py`, after the `ClaimConceptEdge` class (before `Contradiction`), add:

```python
@dataclass(frozen=True, slots=True)
class CustodianSession:
    id: UUID
    user_id: UUID
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    model: str
    provider: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianSession:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            title=row.get("title"),
            started_at=row["started_at"],
            ended_at=row.get("ended_at"),
            model=row["model"],
            provider=row["provider"],
        )


@dataclass(frozen=True, slots=True)
class CustodianMessage:
    id: UUID
    session_id: UUID
    user_id: UUID
    role: str
    content: str
    tool_name: str | None
    tool_input: str | None
    tool_output: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianMessage:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            role=row["role"],
            content=row["content"],
            tool_name=row.get("tool_name"),
            tool_input=row.get("tool_input"),
            tool_output=row.get("tool_output"),
            created_at=row["created_at"],
        )
```

(Both use the same `frozen=True, slots=True` + `from_row` shape as every other model — no new imports needed, `dataclass`, `Mapping`, `Any`, `UUID`, `datetime` are already imported at the top of `kernel/models.py`.)

- [ ] **Step 4: Write the repository**

Create `kernel/db/custodian.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import CustodianMessage, CustodianSession

_SESSION_COLUMNS = "id, user_id, title, started_at, ended_at, model, provider"
_MESSAGE_COLUMNS = (
    "id, session_id, user_id, role, content, tool_name, tool_input, "
    "tool_output, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class CustodianRepository(BaseRepository):
    async def create_session(
        self,
        *,
        user_id: str | UUID,
        model: str,
        provider: str,
        title: str | None = None,
    ) -> CustodianSession:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_sessions (user_id, title, model, provider)
                    VALUES (:user_id, :title, :model, :provider)
                    RETURNING {_SESSION_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "title": strip_nul_bytes(title),
                    "model": model,
                    "provider": provider,
                },
            )
        ).mappings().one()
        return CustodianSession.from_row(_as_mapping(row))

    async def get_session(self, session_id: str | UUID) -> CustodianSession | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_SESSION_COLUMNS} FROM custodian_sessions WHERE id = :id"),
                {"id": str(session_id)},
            )
        ).mappings().first()
        return CustodianSession.from_row(_as_mapping(row)) if row else None

    async def list_sessions(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[CustodianSession]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_SESSION_COLUMNS} FROM custodian_sessions "
                    "ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [CustodianSession.from_row(_as_mapping(r)) for r in rows]

    async def end_session(self, session_id: str | UUID) -> CustodianSession | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE custodian_sessions SET ended_at = now()
                    WHERE id = :id AND ended_at IS NULL
                    RETURNING {_SESSION_COLUMNS}
                    """
                ),
                {"id": str(session_id)},
            )
        ).mappings().first()
        return CustodianSession.from_row(_as_mapping(row)) if row else None

    async def set_title(self, session_id: str | UUID, title: str) -> None:
        await self.conn.execute(
            text(
                "UPDATE custodian_sessions SET title = :title "
                "WHERE id = :id AND title IS NULL"
            ),
            {"id": str(session_id), "title": strip_nul_bytes(title)},
        )

    async def add_message(
        self,
        *,
        session_id: str | UUID,
        user_id: str | UUID,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_input: str | None = None,
        tool_output: str | None = None,
    ) -> CustodianMessage:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_messages
                        (session_id, user_id, role, content, tool_name, tool_input, tool_output)
                    VALUES
                        (:session_id, :user_id, :role, :content, :tool_name, :tool_input, :tool_output)
                    RETURNING {_MESSAGE_COLUMNS}
                    """
                ),
                {
                    "session_id": str(session_id),
                    "user_id": str(user_id),
                    "role": role,
                    "content": strip_nul_bytes(content),
                    "tool_name": tool_name,
                    "tool_input": strip_nul_bytes(tool_input),
                    "tool_output": strip_nul_bytes(tool_output),
                },
            )
        ).mappings().one()
        return CustodianMessage.from_row(_as_mapping(row))

    async def list_messages(self, session_id: str | UUID) -> list[CustodianMessage]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_MESSAGE_COLUMNS} FROM custodian_messages "
                    "WHERE session_id = :session_id ORDER BY created_at ASC"
                ),
                {"session_id": str(session_id)},
            )
        ).mappings().all()
        return [CustodianMessage.from_row(_as_mapping(r)) for r in rows]

    async def count_messages(self, session_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text(
                    "SELECT count(*) FROM custodian_messages WHERE session_id = :session_id"
                ),
                {"session_id": str(session_id)},
            )
        ).scalar_one()
        return result
```

- [ ] **Step 5: Write the failing tests**

Create `tests/kernel/test_custodian_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.custodian import CustodianRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_get_session_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        fetched = await repo.get_session(created.id)

    assert created.title is None
    assert created.ended_at is None
    assert fetched == created


@pytest.mark.asyncio
async def test_list_sessions_orders_newest_first(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        first = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        second = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        listed = await repo.list_sessions()

    assert [s.id for s in listed] == [second.id, first.id]


@pytest.mark.asyncio
async def test_end_session_sets_ended_at_and_is_idempotent(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        ended = await repo.end_session(created.id)
        already_ended = await repo.end_session(created.id)

    assert ended is not None
    assert ended.ended_at is not None
    assert already_ended is None


@pytest.mark.asyncio
async def test_set_title_only_sets_when_null(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        await repo.set_title(created.id, "First title")
        await repo.set_title(created.id, "Second title")
        fetched = await repo.get_session(created.id)

    assert fetched is not None
    assert fetched.title == "First title"


@pytest.mark.asyncio
async def test_add_and_list_messages_in_order(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        custodian_session = await repo.create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        await repo.add_message(
            session_id=custodian_session.id, user_id=user_id, role="user", content="Hi there."
        )
        await repo.add_message(
            session_id=custodian_session.id,
            user_id=user_id,
            role="tool",
            content="",
            tool_name="search_archive",
            tool_input='{"query": "hi"}',
            tool_output="[]",
        )
        await repo.add_message(
            session_id=custodian_session.id, user_id=user_id, role="assistant", content="Hello!"
        )
        messages = await repo.list_messages(custodian_session.id)
        count = await repo.count_messages(custodian_session.id)

    assert [m.role for m in messages] == ["user", "tool", "assistant"]
    assert messages[1].tool_name == "search_archive"
    assert count == 3
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kernel.db.custodian'` (or table-not-found before Step 1/2's migration is applied — run Step 2 first if needed).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_repository.py -v`
Expected: 5 passed.

- [ ] **Step 8: Add tenant isolation coverage**

In `tests/kernel/test_tenant_isolation.py`, add at the end:

```python
@pytest.mark.asyncio
async def test_custodian_isolated_between_tenants(make_user):
    from kernel.db.custodian import CustodianRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_a, model="gpt-4o-mini", provider="openai"
        )
        await CustodianRepository(conn).add_message(
            session_id=custodian_session.id,
            user_id=user_a,
            role="user",
            content="Secret question.",
        )

    async with session(user_b) as conn:
        assert await CustodianRepository(conn).get_session(custodian_session.id) is None
        assert await CustodianRepository(conn).list_sessions() == []
```

Run: `pytest tests/kernel/test_tenant_isolation.py -v`
Expected: all tests pass, including the new one.

- [ ] **Step 9: Add teardown cleanup so DB tests stay isolated**

In `tests/conftest.py`, in the `make_user` fixture's teardown loop, add two lines before `DELETE FROM claim_concept_edges` (messages must go before sessions, and both must go before the user delete outside this block):

```python
            await conn.execute(text("DELETE FROM custodian_messages"))
            await conn.execute(text("DELETE FROM custodian_sessions"))
            await conn.execute(text("DELETE FROM claim_concept_edges"))
```

In `tests/backend/conftest.py`, add the same two lines to both cleanup blocks in `seeded_user` (the `MIGRATION_DATABASE_URL`-scoped block, using the `WHERE user_id IN (SELECT id FROM users WHERE email = :e)` / `WHERE session_id IN (...)` form, and the RLS-scoped teardown block at the bottom):

```python
            await conn.execute(
                text(
                    "DELETE FROM custodian_messages WHERE session_id IN "
                    "(SELECT id FROM custodian_sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :e))"
                ),
                {"e": email},
            )
            await conn.execute(
                text(
                    "DELETE FROM custodian_sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :e)"
                ),
                {"e": email},
            )
```

and, in the RLS-scoped teardown block:

```python
    async with session(uid) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
        await conn.execute(text("DELETE FROM claim_concept_edges"))
```

Run: `pytest tests/kernel/ tests/backend/ -v`
Expected: all pass, no leftover-row failures across test runs.

- [ ] **Step 10: Commit**

```bash
git add migrations/versions/0011_custodian.py kernel/models.py kernel/db/custodian.py \
  tests/kernel/test_custodian_repository.py tests/kernel/test_tenant_isolation.py \
  tests/conftest.py tests/backend/conftest.py
git commit -m "feat: add custodian_sessions/custodian_messages tables, model, and repository"
```

---

### Task 2: Concept name lookup

**Files:**
- Modify: `kernel/db/concepts.py` (add `search_by_name`)
- Modify: `tests/kernel/test_concepts_repository.py` (add a test)

**Interfaces:**
- Produces: `ConceptRepository.search_by_name(query: str, limit: int = 5) -> list[Concept]`.
- Consumes: nothing new — same `Concept` model and `_COLUMNS`/`_as_mapping` already in `kernel/db/concepts.py`.

- [ ] **Step 1: Write the failing test**

In `tests/kernel/test_concepts_repository.py`, add:

```python
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
```

(Check the top of `tests/kernel/test_concepts_repository.py` for existing imports — `ConceptRepository`, `session`, and `pytest` should already be imported; add nothing new.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_concepts_repository.py -k search_by_name -v`
Expected: FAIL — `AttributeError: 'ConceptRepository' object has no attribute 'search_by_name'`.

- [ ] **Step 3: Implement it**

In `kernel/db/concepts.py`, add (after `list`, at the end of the class):

```python
    async def search_by_name(self, query: str, limit: int = 5) -> list[Concept]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM concepts WHERE concept_name ILIKE :pattern "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"pattern": f"%{query}%", "limit": limit},
            )
        ).mappings().all()
        return [Concept.from_row(_as_mapping(r)) for r in rows]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_concepts_repository.py -k search_by_name -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add kernel/db/concepts.py tests/kernel/test_concepts_repository.py
git commit -m "feat: add concept name-substring lookup for Custodian retrieval"
```

---

### Task 3: Conversation engine

**Files:**
- Create: `kernel/ai/custodian.py`
- Create: `tests/kernel/test_custodian_engine.py`

**Interfaces:**
- Produces: `CustodianSettings.from_env()` (`active_ai_provider, openai_api_key, openai_custodian_model, custodian_max_messages_per_session`); `ToolCallRecord` dataclass (`tool_name, tool_input, tool_output`); `CustodianReply` dataclass (`content: str, tool_calls: list[ToolCallRecord]`); `OpenAICustodian(api_key, model, *, client=None)` with `async reply(conn, user_id, history: list[dict[str, str]], on_token: Callable[[str], Awaitable[None]], on_tool_call: Callable[[ToolCallRecord], Awaitable[None]]) -> CustodianReply`; `get_custodian(settings=None) -> OpenAICustodian`.
- Consumes: `kernel.ai.embeddings.EmbeddingSettings`/`get_embedder`, `kernel.db.semantic_vectors.SemanticVectorRepository.search_similar`, `kernel.db.concepts.ConceptRepository.search_by_name` (Task 2), `kernel.db.revisions.RevisionRepository.list`.

- [ ] **Step 1: Write the module**

Create `kernel/ai/custodian.py`:

```python
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository

SYSTEM_PROMPT = (
    "You are the Custodian, a conversational guide to the user's personal "
    "knowledge archive (LociGraph). Use the search_archive tool to find "
    "relevant claims and the search_concepts tool to look up what the "
    "archive knows about a named concept, including how that understanding "
    "has changed over time. Answer only from what these tools return — if "
    "nothing relevant turns up, say so plainly rather than guessing. Be "
    "concise."
)

SEARCH_ARCHIVE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_archive",
    "description": (
        "Semantic search over the user's claims — atomic statements "
        "extracted from their sources. Returns the most relevant claims."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query", "limit"],
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "limit": {"type": "integer", "description": "Max results, 1-20."},
        },
    },
}

SEARCH_CONCEPTS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_concepts",
    "description": (
        "Look up concepts by name (substring match). Returns each match's "
        "description and recent revision history."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query", "limit"],
        "properties": {
            "query": {"type": "string", "description": "Concept name or part of it."},
            "limit": {"type": "integer", "description": "Max results, 1-20."},
        },
    },
}

# ponytail: bounded to 5 tool-call rounds — comfortably above any real chat
# turn (each round can batch multiple parallel tool calls); raise if a real
# conversation ever needs more back-and-forth than this.
_MAX_TOOL_ROUNDS = 5


@dataclass(frozen=True, slots=True)
class CustodianSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_custodian_model: str
    custodian_max_messages_per_session: int

    @classmethod
    def from_env(cls) -> CustodianSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_custodian_model=os.environ.get("OPENAI_CUSTODIAN_MODEL", "gpt-4o-mini"),
            custodian_max_messages_per_session=max(
                1, int(os.environ.get("CUSTODIAN_MAX_MESSAGES_PER_SESSION", "100"))
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    tool_name: str
    tool_input: str
    tool_output: str


@dataclass(frozen=True, slots=True)
class CustodianReply:
    content: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


OnToken = Callable[[str], Awaitable[None]]
OnToolCall = Callable[[ToolCallRecord], Awaitable[None]]


async def _run_search_archive(conn: Any, query: str, limit: int) -> str:
    embedder = get_embedder(EmbeddingSettings.from_env())
    [query_embedding] = await embedder.embed([query])
    results = await SemanticVectorRepository(conn).search_similar(
        query_embedding, limit=max(1, min(limit, 20))
    )
    return json.dumps(
        [
            {
                "claim_text": r.claim.claim_text,
                "claim_type": r.claim.claim_type,
                "assertion_type": r.claim.assertion_type,
                "similarity": r.similarity,
            }
            for r in results
        ]
    )


async def _run_search_concepts(conn: Any, query: str, limit: int) -> str:
    concepts = await ConceptRepository(conn).search_by_name(query, limit=max(1, min(limit, 20)))
    revisions = RevisionRepository(conn)
    payload = []
    for concept in concepts:
        recent = await revisions.list(concept_id=concept.id, limit=5)
        payload.append(
            {
                "concept_name": concept.concept_name,
                "concept_type": concept.concept_type,
                "description": concept.description,
                "recent_revisions": [
                    {
                        "new_description": r.new_description,
                        "rationale": r.rationale,
                        "source": r.source,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in recent
                ],
            }
        )
    return json.dumps(payload)


class OpenAICustodian:
    def __init__(self, api_key: str, model: str, *, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        # Injected in tests; created lazily in reply() otherwise — every
        # other kernel/ai/*.py module constructs AsyncOpenAI() inline per
        # call instead of storing it, but this module's tool-call loop is
        # non-trivial new logic worth unit-testing directly, so it accepts
        # an injected client the way no prior module here needed to.
        self._client = client

    async def reply(
        self,
        conn: Any,
        user_id: str | UUID,
        history: list[dict[str, str]],
        on_token: OnToken,
        on_tool_call: OnToolCall,
    ) -> CustodianReply:
        client = self._client
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

        tool_calls: list[ToolCallRecord] = []
        content_parts: list[str] = []
        input_items: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
        ]
        previous_response_id: str | None = None

        for _ in range(_MAX_TOOL_ROUNDS):
            async with client.responses.stream(
                model=self.model,
                input=input_items,
                tools=[SEARCH_ARCHIVE_TOOL, SEARCH_CONCEPTS_TOOL],
                previous_response_id=previous_response_id,
            ) as stream:
                async for event in stream:
                    if event.type == "response.output_text.delta":
                        content_parts.append(event.delta)
                        await on_token(event.delta)
                response = await stream.get_final_response()

            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            follow_up: list[dict[str, Any]] = []
            for call in function_calls:
                args = json.loads(call.arguments)
                if call.name == "search_archive":
                    output = await _run_search_archive(conn, args["query"], args["limit"])
                elif call.name == "search_concepts":
                    output = await _run_search_concepts(conn, args["query"], args["limit"])
                else:
                    output = json.dumps({"error": f"unknown tool {call.name}"})
                record = ToolCallRecord(
                    tool_name=call.name, tool_input=call.arguments, tool_output=output
                )
                tool_calls.append(record)
                await on_tool_call(record)
                follow_up.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": output}
                )
            input_items = follow_up
            previous_response_id = response.id

        return CustodianReply(content="".join(content_parts), tool_calls=tool_calls)


def get_custodian(settings: CustodianSettings | None = None) -> OpenAICustodian:
    settings = settings or CustodianSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAICustodian(settings.openai_api_key, settings.openai_custodian_model)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/kernel/test_custodian_engine.py`:

```python
from __future__ import annotations

import json

import pytest

from kernel.ai.custodian import (
    CustodianSettings,
    OpenAICustodian,
    ToolCallRecord,
    _run_search_archive,
    _run_search_concepts,
)
from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session


def _pad_vector(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


class FakeEmbedder:
    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return [_pad_vector([float(len(t)), 0.0]) for t in texts]


class _Delta:
    def __init__(self, delta: str) -> None:
        self.type = "response.output_text.delta"
        self.delta = delta


class _FunctionCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.type = "function_call"
        self.call_id = call_id
        self.name = name
        self.arguments = arguments


class _FakeResponse:
    def __init__(self, id_: str, output: list[object]) -> None:
        self.id = id_
        self.output = output


class _FakeStream:
    def __init__(self, events: list[object], response: _FakeResponse) -> None:
        self._events = events
        self._response = response

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def _aiter(self):  # type: ignore[no-untyped-def]
        for event in self._events:
            yield event

    def __aiter__(self):  # type: ignore[no-untyped-def]
        return self._aiter()

    async def get_final_response(self) -> _FakeResponse:
        return self._response


class _FakeResponsesClient:
    def __init__(self, rounds: list[tuple[list[object], _FakeResponse]]) -> None:
        self._rounds = list(rounds)
        self.calls: list[dict[str, object]] = []

    def stream(self, **kwargs: object) -> _FakeStream:
        self.calls.append(kwargs)
        events, response = self._rounds.pop(0)
        return _FakeStream(events, response)


class FakeOpenAIClient:
    def __init__(self, rounds: list[tuple[list[object], _FakeResponse]]) -> None:
        self.responses = _FakeResponsesClient(rounds)


async def _collect_reply(custodian, conn, user_id, history):  # type: ignore[no-untyped-def]
    tokens: list[str] = []
    tool_calls: list[ToolCallRecord] = []

    async def on_token(delta: str) -> None:
        tokens.append(delta)

    async def on_tool_call(record: ToolCallRecord) -> None:
        tool_calls.append(record)

    reply = await custodian.reply(conn, user_id, history, on_token, on_tool_call)
    return reply, tokens, tool_calls


@pytest.mark.asyncio
async def test_reply_with_no_tool_call_streams_and_assembles_content(make_user):
    user_id = await make_user()
    fake_client = FakeOpenAIClient(
        [([_Delta("Hello"), _Delta(" there.")], _FakeResponse("resp_1", []))]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        reply, tokens, tool_calls = await _collect_reply(
            custodian, conn, user_id, [{"role": "user", "content": "hi"}]
        )

    assert tokens == ["Hello", " there."]
    assert reply.content == "Hello there."
    assert tool_calls == []
    assert fake_client.responses.calls[0]["previous_response_id"] is None


@pytest.mark.asyncio
async def test_reply_executes_search_concepts_tool_and_continues(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await ConceptRepository(conn).create(
            user_id=user_id,
            concept_name="Sovereignty",
            concept_type="value",
            description="Self-determination.",
        )

    call_args = json.dumps({"query": "Sovereignty", "limit": 5})
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse(
                    "resp_1",
                    [_FunctionCall("call_1", "search_concepts", call_args)],
                ),
            ),
            ([_Delta("It means self-determination.")], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        reply, tokens, tool_calls = await _collect_reply(
            custodian, conn, user_id, [{"role": "user", "content": "What is Sovereignty?"}]
        )

    assert reply.content == "It means self-determination."
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "search_concepts"
    output = json.loads(tool_calls[0].tool_output)
    assert output[0]["concept_name"] == "Sovereignty"
    second_call = fake_client.responses.calls[1]
    assert second_call["previous_response_id"] == "resp_1"
    assert second_call["input"][0]["call_id"] == "call_1"


@pytest.mark.asyncio
async def test_run_search_archive_returns_matching_claims(make_user, monkeypatch):
    from kernel.db.claims import ClaimRepository
    from kernel.db.observations import ObservationRepository
    from kernel.db.sources import SourceRepository

    user_id = await make_user()
    monkeypatch.setattr("kernel.ai.custodian.get_embedder", lambda settings: FakeEmbedder())

    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "custodian-engine-1")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained yesterday."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="It rained yesterday.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        from kernel.db.semantic_vectors import SemanticVectorRepository

        await SemanticVectorRepository(conn).create(
            user_id=user_id,
            claim_id=claim.id,
            model_name="fake",
            embedding=_pad_vector([1.0, 0.0]),
        )

        output = json.loads(await _run_search_archive(conn, "weather", 5))

    assert output[0]["claim_text"] == "It rained yesterday."


@pytest.mark.asyncio
async def test_run_search_concepts_includes_revision_history(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id,
            concept_name="Sovereignty",
            concept_type="value",
            description="Self-determination.",
        )
        assert concept is not None
        await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Self-determination, updated.",
            rationale="Clarified wording.",
        )

        output = json.loads(await _run_search_concepts(conn, "sovereign", 5))

    assert output[0]["concept_name"] == "Sovereignty"
    assert output[0]["recent_revisions"][0]["new_description"] == "Self-determination, updated."


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CUSTODIAN_MODEL", raising=False)
    monkeypatch.delenv("CUSTODIAN_MAX_MESSAGES_PER_SESSION", raising=False)

    settings = CustodianSettings.from_env()

    assert settings.openai_custodian_model == "gpt-4o-mini"
    assert settings.custodian_max_messages_per_session == 100
```

Check `kernel/db/semantic_vectors.py`'s `create` signature before running this (`SemanticVectorRepository(conn).create(*, user_id, claim_id, model_name, embedding)`) — it matches the constructor used in `tests/worker/test_embed_claims.py` and other semantic-vector tests already in this codebase.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kernel.ai.custodian'`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_engine.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add kernel/ai/custodian.py tests/kernel/test_custodian_engine.py
git commit -m "feat: add Custodian conversation engine with search_archive/search_concepts tools"
```

---

### Task 4: Backend API

**Files:**
- Create: `backend/app/api/custodian.py`
- Modify: `backend/app/main.py` (register the router)
- Create: `tests/backend/test_custodian_api.py`

**Interfaces:**
- Produces: `POST /custodian/sessions`, `GET /custodian/sessions`, `GET /custodian/sessions/{id}/messages`, `POST /custodian/sessions/{id}/messages` (SSE), `POST /custodian/sessions/{id}/end`.
- Consumes: `kernel.db.custodian.CustodianRepository` (Task 1), `kernel.ai.custodian.CustodianSettings`/`get_custodian`/`ToolCallRecord` (Task 3), `backend.app.auth.dependencies.get_current_user`, `kernel.db.session.session`.

- [ ] **Step 1: Write the router**

Create `backend/app/api/custodian.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from kernel.ai.custodian import CustodianSettings, ToolCallRecord, get_custodian
from kernel.db.custodian import CustodianRepository
from kernel.db.session import session
from kernel.models import CustodianMessage, CustodianSession

logger = logging.getLogger(__name__)

router = APIRouter()

# Fire-and-forget background tasks: Python only guarantees a task stays alive
# while something holds a strong reference to it, so a bare
# `asyncio.create_task(...)` risks the task being garbage-collected mid-flight.
# This module-level set is the standard workaround (add on create, discard on
# completion via a done-callback).
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class CreateSessionBody(BaseModel):
    title: str | None = None


class MessageBody(BaseModel):
    content: str


def _serialize_session(s: CustodianSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "title": s.title,
        "started_at": s.started_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "model": s.model,
        "provider": s.provider,
    }


def _serialize_message(m: CustodianMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "session_id": str(m.session_id),
        "role": m.role,
        "content": m.content,
        "tool_name": m.tool_name,
        "tool_input": m.tool_input,
        "tool_output": m.tool_output,
        "created_at": m.created_at.isoformat(),
    }


@router.post("/custodian/sessions")
async def create_custodian_session(
    body: CreateSessionBody, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    settings = CustodianSettings.from_env()
    async with session(user_id) as conn:
        created = await CustodianRepository(conn).create_session(
            user_id=user_id,
            model=settings.openai_custodian_model,
            provider=settings.active_ai_provider,
            title=body.title,
        )
    return _serialize_session(created)


@router.get("/custodian/sessions")
async def list_custodian_sessions(
    limit: int = 50, offset: int = 0, user_id: str = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        sessions = await CustodianRepository(conn).list_sessions(limit=limit, offset=offset)
    return [_serialize_session(s) for s in sessions]


@router.get("/custodian/sessions/{session_id}/messages")
async def get_custodian_messages(
    session_id: str, user_id: str = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        if await repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="not found")
        messages = await repo.list_messages(session_id)
    return [_serialize_message(m) for m in messages]


@router.post("/custodian/sessions/{session_id}/end")
async def end_custodian_session(
    session_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    async with session(user_id) as conn:
        ended = await CustodianRepository(conn).end_session(session_id)
        if ended is None:
            raise HTTPException(status_code=404, detail="not found or already ended")
    return _serialize_session(ended)


async def _generate_and_persist(
    session_id: UUID, user_id: str, queue: asyncio.Queue[dict[str, Any] | None]
) -> None:
    """Runs as a detached background task, independent of the HTTP response
    lifecycle — persists the reply regardless of whether the client is still
    listening. Puts SSE-shaped events on `queue`, then `None` to signal done."""
    try:
        async with session(user_id) as conn:
            repo = CustodianRepository(conn)
            history = [
                {"role": m.role, "content": m.content}
                for m in await repo.list_messages(session_id)
                if m.role in ("user", "assistant")
            ]
            custodian = get_custodian()

            async def on_token(delta: str) -> None:
                await queue.put({"event": "token", "data": {"delta": delta}})

            async def on_tool_call(record: ToolCallRecord) -> None:
                query = json.loads(record.tool_input).get("query", "")
                await queue.put(
                    {
                        "event": "tool_call",
                        "data": {"tool_name": record.tool_name, "query": query},
                    }
                )

            reply = await custodian.reply(conn, user_id, history, on_token, on_tool_call)

            for call in reply.tool_calls:
                await repo.add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="tool",
                    content="",
                    tool_name=call.tool_name,
                    tool_input=call.tool_input,
                    tool_output=call.tool_output,
                )
            await repo.add_message(
                session_id=session_id, user_id=user_id, role="assistant", content=reply.content
            )
        await queue.put({"event": "done", "data": {}})
    except Exception as exc:
        logger.warning("custodian reply failed for session %s: %s", session_id, exc)
        try:
            async with session(user_id) as conn:
                await CustodianRepository(conn).add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="system",
                    content="The Custodian couldn't respond. Please try again.",
                )
        except Exception:
            logger.exception("failed to persist custodian error message for session %s", session_id)
        await queue.put({"event": "error", "data": {"message": "generation failed"}})
    finally:
        await queue.put(None)


@router.post("/custodian/sessions/{session_id}/messages")
async def send_custodian_message(
    session_id: str, body: MessageBody, user_id: str = Depends(get_current_user)
) -> StreamingResponse:
    settings = CustodianSettings.from_env()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        custodian_session = await repo.get_session(session_id)
        if custodian_session is None:
            raise HTTPException(status_code=404, detail="not found")
        message_count = await repo.count_messages(session_id)
        if (
            custodian_session.ended_at is not None
            or message_count >= settings.custodian_max_messages_per_session
        ):
            if custodian_session.ended_at is None:
                await repo.end_session(session_id)
            raise HTTPException(
                status_code=409,
                detail="this conversation has reached its message limit — start a new one",
            )
        await repo.add_message(
            session_id=session_id, user_id=user_id, role="user", content=body.content
        )
        if custodian_session.title is None:
            await repo.set_title(session_id, body.content[:60])

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    _spawn(_generate_and_persist(UUID(session_id), user_id, queue))

    async def event_stream() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 2: Register the router**

In `backend/app/main.py`, add the import and registration:

```python
from backend.app.api import (
    auth,
    claims,
    concepts,
    contradictions,
    custodian,
    dashboard,
    jobs,
    observations,
    search,
    sources,
)


def create_app() -> FastAPI:
    app = FastAPI(title="LociGraph")
    app.include_router(auth.router)
    app.include_router(sources.router)
    app.include_router(observations.router)
    app.include_router(jobs.router)
    app.include_router(dashboard.router)
    app.include_router(claims.router)
    app.include_router(concepts.router)
    app.include_router(contradictions.router)
    app.include_router(custodian.router)
    app.include_router(search.router)
    return app
```

- [ ] **Step 3: Write the failing tests**

Create `tests/backend/test_custodian_api.py`:

```python
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

from kernel.ai.custodian import CustodianReply, ToolCallRecord
from kernel.db.custodian import CustodianRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


class FakeCustodian:
    def __init__(self, reply: CustodianReply) -> None:
        self._reply = reply

    async def reply(self, conn, user_id, history, on_token, on_tool_call):  # type: ignore[no-untyped-def]
        for chunk in self._reply.content.split(" "):
            await on_token(chunk + " ")
        for call in self._reply.tool_calls:
            await on_tool_call(call)
        return self._reply


async def _drain_sse(response) -> list[tuple[str, dict]]:  # type: ignore[no-untyped-def]
    events = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            lines = raw.split("\n")
            event = next(l[len("event: "):] for l in lines if l.startswith("event: "))
            data = json.loads(next(l[len("data: "):] for l in lines if l.startswith("data: ")))
            events.append((event, data))
    return events


@pytest.mark.asyncio
async def test_create_and_list_sessions(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    listed = await client.get("/custodian/sessions")

    assert created.status_code == 200
    assert created.json()["title"] is None
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == created.json()["id"]

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_send_message_streams_tokens_and_persists_reply(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    fake = FakeCustodian(
        CustodianReply(
            content="Hello there.",
            tool_calls=[
                ToolCallRecord(
                    tool_name="search_archive",
                    tool_input=json.dumps({"query": "hi", "limit": 5}),
                    tool_output="[]",
                )
            ],
        )
    )
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    session_id = created.json()["id"]

    async with client.stream(
        "POST", f"/custodian/sessions/{session_id}/messages", json={"content": "Hi"}
    ) as response:
        events = await _drain_sse(response)

    assert ("done", {}) in events
    assert any(e == "tool_call" and d["tool_name"] == "search_archive" for e, d in events)
    assert any(e == "token" for e, _ in events)

    async with session(seeded_user) as conn:
        messages = await CustodianRepository(conn).list_messages(session_id)
    roles = [m.role for m in messages]
    assert roles == ["user", "tool", "assistant"]
    assert messages[0].content == "Hi"
    assert messages[2].content == "Hello there."

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_send_message_404s_for_unknown_session(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/custodian/sessions/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "Hi"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_send_message_409s_once_message_cap_is_hit(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    monkeypatch.setenv("CUSTODIAN_MAX_MESSAGES_PER_SESSION", "1")
    fake = FakeCustodian(CustodianReply(content="ok", tool_calls=[]))
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    session_id = created.json()["id"]

    async with client.stream(
        "POST", f"/custodian/sessions/{session_id}/messages", json={"content": "Hi"}
    ) as first:
        await _drain_sse(first)

    second = await client.post(
        f"/custodian/sessions/{session_id}/messages", json={"content": "Again"}
    )

    assert second.status_code == 409

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pytest tests/backend/test_custodian_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.api.custodian'`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/backend/test_custodian_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest tests/kernel/ tests/backend/ -v`
Expected: all pass — confirms the new router doesn't break existing endpoints and teardown ordering is correct.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/custodian.py backend/app/main.py tests/backend/test_custodian_api.py
git commit -m "feat: add Custodian session CRUD and SSE message-streaming API"
```

---

### Task 5: Frontend types and API client

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `CustodianSession`, `CustodianMessage`)
- Modify: `frontend/src/lib/api.ts` (add Custodian client functions)

**Interfaces:**
- Produces: `CustodianSession`, `CustodianMessage`, `CustodianStreamHandlers` types; `createCustodianSession`, `listCustodianSessions`, `getCustodianMessages`, `streamCustodianMessage`, `endCustodianSession` functions.
- Consumes: `req`, `readError`, `JSON_HEADERS`, `base` already in `frontend/src/lib/api.ts`.

- [ ] **Step 1: Add the types**

In `frontend/src/lib/types.ts`, add (near `Revision`):

```typescript
export interface CustodianSession {
  id: string
  title: string | null
  startedAt: string
  endedAt: string | null
  model: string
  provider: string
}

export type CustodianMessageRole = "user" | "assistant" | "tool" | "system"

export interface CustodianMessage {
  id: string
  sessionId: string
  role: CustodianMessageRole
  content: string
  toolName: string | null
  toolInput: string | null
  toolOutput: string | null
  createdAt: string
}
```

- [ ] **Step 2: Add the API client functions**

In `frontend/src/lib/api.ts`, add `CustodianSession`, `CustodianMessage` to the type-only import at the top, then add at the end of the file:

```typescript
function toCustodianSession(d: Record<string, unknown>): CustodianSession {
  return {
    id: String(d.id),
    title: (d.title as string | null) ?? null,
    startedAt: String(d.started_at),
    endedAt: (d.ended_at as string | null) ?? null,
    model: String(d.model),
    provider: String(d.provider),
  }
}

function toCustodianMessage(d: Record<string, unknown>): CustodianMessage {
  return {
    id: String(d.id),
    sessionId: String(d.session_id),
    role: d.role as CustodianMessage["role"],
    content: String(d.content),
    toolName: (d.tool_name as string | null) ?? null,
    toolInput: (d.tool_input as string | null) ?? null,
    toolOutput: (d.tool_output as string | null) ?? null,
    createdAt: String(d.created_at),
  }
}

export async function createCustodianSession(title: string | null = null): Promise<CustodianSession> {
  const r = await req("/custodian/sessions", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ title }),
  })
  if (!r.ok) throw await readError(r, "createCustodianSession failed")
  return toCustodianSession(await r.json())
}

export async function listCustodianSessions(): Promise<CustodianSession[]> {
  const r = await req("/custodian/sessions")
  if (!r.ok) throw await readError(r, "listCustodianSessions failed")
  return (await r.json()).map(toCustodianSession)
}

export async function getCustodianMessages(sessionId: string): Promise<CustodianMessage[]> {
  const r = await req(`/custodian/sessions/${sessionId}/messages`)
  if (!r.ok) throw await readError(r, "getCustodianMessages failed")
  return (await r.json()).map(toCustodianMessage)
}

export async function endCustodianSession(sessionId: string): Promise<CustodianSession> {
  const r = await req(`/custodian/sessions/${sessionId}/end`, { method: "POST" })
  if (!r.ok) throw await readError(r, "endCustodianSession failed")
  return toCustodianSession(await r.json())
}

export interface CustodianStreamHandlers {
  onToken(delta: string): void
  onToolCall(toolName: string, query: string): void
  onDone(): void
  onError(message: string): void
}

export async function streamCustodianMessage(
  sessionId: string,
  content: string,
  handlers: CustodianStreamHandlers
): Promise<void> {
  const r = await fetch(base(`/custodian/sessions/${sessionId}/messages`), {
    method: "POST",
    credentials: "include",
    headers: JSON_HEADERS,
    body: JSON.stringify({ content }),
  })
  if (!r.ok || !r.body) {
    const err = await readError(r, "streamCustodianMessage failed")
    handlers.onError(err.message)
    return
  }
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split("\n\n")
    buffer = events.pop() ?? ""
    for (const raw of events) {
      const lines = raw.split("\n")
      const eventLine = lines.find((l) => l.startsWith("event: "))
      const dataLine = lines.find((l) => l.startsWith("data: "))
      if (!eventLine || !dataLine) continue
      const eventName = eventLine.slice("event: ".length)
      const data = JSON.parse(dataLine.slice("data: ".length))
      if (eventName === "token") handlers.onToken(data.delta)
      else if (eventName === "tool_call") handlers.onToolCall(data.tool_name, data.query)
      else if (eventName === "done") handlers.onDone()
      else if (eventName === "error") handlers.onError(data.message)
    }
  }
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: add Custodian types and API client (incl. SSE stream reader)"
```

---

### Task 6: Orb and chat panel UI

**Files:**
- Create: `frontend/src/components/custodian/Orb.tsx`
- Create: `frontend/src/components/custodian/CustodianPanel.tsx`
- Create: `frontend/src/components/custodian/custodian.test.tsx`
- Modify: `frontend/src/app/globals.css` (add the breathing-pulse keyframes)
- Modify: `frontend/src/components/layout/AppChrome.tsx` (render `Orb`, remove its `data-orb-slot` placeholder)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (remove its two `data-orb-slot` placeholders — the Orb now lives in `AppChrome`, not the sidebar)

**Interfaces:**
- Produces: `Orb` component (no props — self-contained, renders its own panel).
- Consumes: `createCustodianSession`, `listCustodianSessions`, `getCustodianMessages`, `streamCustodianMessage`, `endCustodianSession` (Task 5), `useMode` from `@/lib/theme`.

- [ ] **Step 1: Add the pulse animation**

In `frontend/src/app/globals.css`, add at the end:

```css
@keyframes orb-breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.85;
  }
  50% {
    transform: scale(1.08);
    opacity: 1;
  }
}
```

- [ ] **Step 2: Write the chat panel**

Create `frontend/src/components/custodian/CustodianPanel.tsx`:

```tsx
"use client"

import { useEffect, useRef, useState } from "react"
import {
  createCustodianSession,
  endCustodianSession,
  getCustodianMessages,
  listCustodianSessions,
  streamCustodianMessage,
} from "@/lib/api"
import type { CustodianMessage, CustodianSession } from "@/lib/types"

interface DisplayMessage {
  role: CustodianMessage["role"]
  content: string
}

function toDisplay(m: CustodianMessage): DisplayMessage {
  if (m.role === "tool") {
    return { role: "tool", content: `Searched the archive for "${m.toolInput ?? ""}"` }
  }
  return { role: m.role, content: m.content }
}

export function CustodianPanel({ onClose }: { onClose: () => void }) {
  const [sessions, setSessions] = useState<CustodianSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listCustodianSessions().then(setSessions).catch(() => setSessions([]))
  }, [])

  useEffect(() => {
    if (!activeId) {
      setMessages([])
      return
    }
    getCustodianMessages(activeId).then((msgs) => setMessages(msgs.map(toDisplay)))
  }, [activeId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function startNewConversation() {
    const created = await createCustodianSession()
    setSessions((prev) => [created, ...prev])
    setActiveId(created.id)
  }

  async function send() {
    const content = input.trim()
    if (!content || sending) return
    setError(null)
    let sessionId = activeId
    if (!sessionId) {
      const created = await createCustodianSession()
      setSessions((prev) => [created, ...prev])
      setActiveId(created.id)
      sessionId = created.id
    }
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content }])
    setSending(true)
    let assistantSoFar = ""
    setMessages((prev) => [...prev, { role: "assistant", content: "" }])
    await streamCustodianMessage(sessionId, content, {
      onToken(delta) {
        assistantSoFar += delta
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { role: "assistant", content: assistantSoFar }
          return next
        })
      },
      onToolCall(toolName, query) {
        setMessages((prev) => {
          const next = [...prev]
          next.splice(next.length - 1, 0, {
            role: "tool",
            content: `Searched the archive for "${query}"`,
          })
          return next
        })
      },
      onDone() {
        setSending(false)
      },
      onError(message) {
        setSending(false)
        setError(message)
      },
    })
  }

  async function endActive() {
    if (!activeId) return
    await endCustodianSession(activeId)
    setActiveId(null)
  }

  return (
    <div className="fixed bottom-24 right-6 z-50 w-96 h-[32rem] bg-surface border border-hairline rounded-hearth shadow-lg flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
        <span className="font-heading text-sm text-ink">Custodian</span>
        <div className="flex items-center gap-2">
          <button
            onClick={startNewConversation}
            className="text-xs font-ui text-muted hover:text-ink"
          >
            New
          </button>
          <button onClick={onClose} aria-label="Close" className="text-xs font-ui text-muted hover:text-ink">
            Close
          </button>
        </div>
      </div>
      {sessions.length > 0 && (
        <div className="flex gap-1 px-4 py-2 border-b border-hairline overflow-x-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              className={[
                "px-2 py-1 rounded-meridian text-xs font-ui whitespace-nowrap",
                s.id === activeId ? "bg-surface-hover text-accent" : "text-muted",
              ].join(" ")}
            >
              {s.title ?? "New conversation"}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "tool"
                ? "text-xs text-muted italic"
                : m.role === "user"
                  ? "text-sm text-ink text-right"
                  : "text-sm text-ink"
            }
          >
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error && <div className="px-4 py-1 text-xs text-status-failed">{error}</div>}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-hairline">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !sending) send()
          }}
          placeholder="Ask the Custodian..."
          className="flex-1 bg-canvas border border-hairline rounded-meridian px-3 py-1.5 text-sm text-ink outline-none focus:border-accent"
        />
        <button
          onClick={send}
          disabled={sending}
          className="px-3 py-1.5 rounded-meridian bg-accent text-canvas text-xs font-ui disabled:opacity-50"
        >
          Send
        </button>
      </div>
      {activeId && (
        <button onClick={endActive} className="px-4 py-2 text-xs font-ui text-muted hover:text-ink border-t border-hairline">
          End conversation
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Write the Orb**

Create `frontend/src/components/custodian/Orb.tsx`:

```tsx
"use client"

import { useState } from "react"
import { useMode } from "@/lib/theme"
import { CustodianPanel } from "@/components/custodian/CustodianPanel"

export function Orb() {
  const { mode } = useMode()
  const [open, setOpen] = useState(false)
  const isHearth = mode === "hearth"

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open the Custodian"
        data-orb-slot
        className={[
          "fixed z-50 w-14 h-14 rounded-full [animation:orb-breathe_1.4s_ease-in-out_infinite]",
          isHearth
            ? "bottom-6 right-6 bg-accent shadow-[0_0_24px_rgba(45,106,106,0.35)]"
            : "bottom-6 right-6 bg-ember shadow-[0_0_24px_rgba(212,136,47,0.35)]",
        ].join(" ")}
      />
      {open && <CustodianPanel onClose={() => setOpen(false)} />}
    </>
  )
}
```

- [ ] **Step 4: Wire it into AppChrome and remove the old placeholders**

In `frontend/src/components/layout/AppChrome.tsx`, add the import:

```tsx
import { Orb } from "@/components/custodian/Orb"
```

Replace:

```tsx
            {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
            <div data-orb-slot className="hidden" aria-hidden="true" />
```

with nothing (just remove those two lines — the header's right-side `div` still has `ModeToggle`) and add `<Orb />` once, right after the closing `</div>` of the top-level `min-h-screen` wrapper's children, i.e. as the last child of the outermost `<div className="min-h-screen bg-canvas">`:

```tsx
  return (
    <div className="min-h-screen bg-canvas">
      {/* Mode-adaptive sidebar */}
      <Sidebar />

      {/* Main content area shifted by sidebar width */}
      <div className={isHearth ? "ml-60" : "ml-16"}>
        {/* ... header and main unchanged ... */}
      </div>

      <Orb />
    </div>
  )
```

In `frontend/src/components/layout/Sidebar.tsx`, remove both placeholder blocks (one in `HearthSidebar`, one in `MeridianSidebar`):

```tsx
      {/* Orb placeholder */}
      <div className="px-6 mt-auto mb-4">
        {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
        <div data-orb-slot className="hidden" aria-hidden="true" />
      </div>
```

and

```tsx
      {/* Orb placeholder */}
      <div className="mt-auto mb-2">
        {/* Orb/Core companion — deferred (Plan 4 scope: dual-mode, Orb later) */}
        <div data-orb-slot className="hidden" aria-hidden="true" />
      </div>
```

(Sidebar's "Footer utility links" / "Footer icon" blocks that follow each removed placeholder stay as-is.)

- [ ] **Step 5: Write the tests**

Create `frontend/src/components/custodian/custodian.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import { Orb } from "@/components/custodian/Orb"

vi.mock("@/lib/api", () => ({
  createCustodianSession: vi.fn(),
  listCustodianSessions: vi.fn().mockResolvedValue([]),
  getCustodianMessages: vi.fn().mockResolvedValue([]),
  endCustodianSession: vi.fn(),
  streamCustodianMessage: vi.fn(),
}))

import {
  createCustodianSession,
  listCustodianSessions,
  streamCustodianMessage,
} from "@/lib/api"
const mockCreate = vi.mocked(createCustodianSession)
const mockList = vi.mocked(listCustodianSessions)
const mockStream = vi.mocked(streamCustodianMessage)

function renderOrb() {
  return render(
    <ThemeProvider>
      <Orb />
    </ThemeProvider>,
  )
}

describe("Orb", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue([])
  })

  it("opens the chat panel on click", async () => {
    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))

    expect(screen.getByPlaceholderText("Ask the Custodian...")).toBeInTheDocument()
  })

  it("creates a session lazily and streams a reply on first send", async () => {
    mockCreate.mockResolvedValueOnce({
      id: "s1",
      title: null,
      startedAt: "2024-05-12T14:32:01Z",
      endedAt: null,
      model: "gpt-4o-mini",
      provider: "openai",
    })
    mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
      handlers.onToken("Hello")
      handlers.onDone()
    })

    renderOrb()
    await userEvent.click(screen.getByLabelText("Open the Custodian"))
    await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "Hi")
    await userEvent.keyboard("{Enter}")

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalled()
      expect(mockStream).toHaveBeenCalledWith("s1", "Hi", expect.anything())
      expect(screen.getByText("Hello")).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 6: Run the frontend tests**

Run: `cd frontend && npx vitest run src/components/custodian/custodian.test.tsx`
Expected: 2 passed.

- [ ] **Step 7: Run the full frontend test suite and type-check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass, no type errors (confirms removing the `data-orb-slot` placeholders didn't break any existing test asserting on them — search first: `grep -rn "data-orb-slot" frontend/src` should now show zero matches outside `Orb.tsx` itself).

- [ ] **Step 8: Manual smoke check**

Run: `cd frontend && npm run dev`, open the app, confirm the Orb pulses in the bottom-right corner in both Hearth and Meridian mode (toggle via the mode switch), click it to open the panel, send a message (requires `OPENAI_API_KEY` set on the backend to get a real reply — otherwise expect the "couldn't respond" system message, which still confirms the wiring works end-to-end).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/custodian frontend/src/app/globals.css \
  frontend/src/components/layout/AppChrome.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add Orb companion and Custodian chat panel to the frontend"
```

---

### Task 7: Docs

**Files:**
- Modify: `README.md` (add a "Phase 3 Custodian Core" section)
- Modify: `.env.example` (add Custodian env vars)
- Modify: `docker-compose.yml` (add Custodian env vars to `backend` and `worker` services)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add env vars to `.env.example`**

In `.env.example`, after `OPENAI_REVISION_MODEL=gpt-4o-mini`, add:

```
OPENAI_CUSTODIAN_MODEL=gpt-4o-mini
CUSTODIAN_MAX_MESSAGES_PER_SESSION=100
```

- [ ] **Step 2: Add env vars to `docker-compose.yml`**

In both the `backend` and `worker` services' `environment:` blocks, after `OPENAI_REVISION_MODEL: ${OPENAI_REVISION_MODEL:-gpt-4o-mini}`, add:

```yaml
      OPENAI_CUSTODIAN_MODEL: ${OPENAI_CUSTODIAN_MODEL:-gpt-4o-mini}
      CUSTODIAN_MAX_MESSAGES_PER_SESSION: ${CUSTODIAN_MAX_MESSAGES_PER_SESSION:-100}
```

(Worker doesn't call the Custodian directly, but every other AI-related env var is mirrored into both services in this file already — matching that existing convention rather than special-casing this one.)

- [ ] **Step 3: Add the README section and env var table rows**

In `README.md`, after the "Phase 2 Revisions" section and before "## Project Layout", add:

```markdown
## Phase 3 Custodian Core

The Custodian is a conversational guide to the archive — a chat interface,
not a background job. `POST /api/custodian/sessions` starts a session;
`POST /api/custodian/sessions/{id}/messages` streams the reply back over
`text/event-stream` as the model generates it. The model has two read-only
tools: `search_archive` (semantic search over claim embeddings, reusing
Phase 1 Plan 3's embedding index) and `search_concepts` (name-substring
lookup returning a concept's description and revision history). Generation
runs in a detached background task, so closing the chat mid-reply doesn't
truncate what gets saved.

A floating Orb — pulsing in the bottom-right corner on every authenticated
page — opens the chat panel. Custodian Logging (letting the model propose
new observations/claims/concepts from chat) and contradiction-classification
assistance are separate follow-up plans; see
[docs/superpowers/specs/2026-07-09-custodian-core-design.md](docs/superpowers/specs/2026-07-09-custodian-core-design.md).
```

In the environment variables table, after the `OPENAI_EXTRACTION_MODEL`/`CLAIM_EXTRACTION_AUTORUN`/`CLAIM_EXTRACTION_BATCH_SIZE` rows (or wherever the table currently ends, before `COOKIE_SECURE`), add:

```markdown
| `OPENAI_CUSTODIAN_MODEL` | no | OpenAI model used by the Custodian chat (default: `gpt-4o-mini`) |
| `CUSTODIAN_MAX_MESSAGES_PER_SESSION` | no | Messages allowed per chat session before it auto-ends (default: `100`) |
```

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example docker-compose.yml
git commit -m "docs: document Custodian Core chat, retrieval tools, and env vars"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest && (cd frontend && npx vitest run && npx tsc --noEmit)`
- [ ] Run `alembic check` to confirm no unapplied migrations.
- [ ] Run `ruff check kernel/ backend/ worker/` and `mypy kernel/ backend/ worker/`.
- [ ] Manually smoke-test the Orb in both Hearth and Meridian mode per Task 6 Step 8.
