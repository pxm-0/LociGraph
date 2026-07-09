# Custodian Logging (Phase 3 Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Custodian propose new archive memory during chat — nine kinds of proposals across five freestanding creates and four actions on an existing row — with nothing canonical until the user explicitly accepts it.

**Architecture:** A generic `custodian_logged_items` table (`proposed`/`accepted`/`rejected`/`superseded`) holds every proposal. `kernel/custodian_logging.py` is the pure orchestration layer — `accept_logged_item`/`reject_logged_item` compose the existing repositories (`ObservationRepository`, `ClaimRepository`, `ConceptCandidateRepository`, `ContradictionRepository`) plus two new ones (`NoteRepository`, `ImportanceSignalRepository`) to perform the real write, exactly the way `kernel/concepts_promotion.py`'s `approve_candidate` composes repos over one connection. `kernel/ai/custodian.py` (Custodian Core) grows from 2 tools to 11 — nine `propose_*` tools, each inserting a `proposed` row and nothing else. The API exposes list/accept/reject endpoints; the chat panel renders each proposal as an inline card with Accept/Reject buttons.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries), asyncpg, Postgres 16, OpenAI Responses API function tools, Next.js/React/TypeScript, pytest + vitest.

**Depends on:** Phase 3 Plan 1 (Custodian Core) — reuses `custodian_sessions`/`custodian_messages`, extends `OpenAICustodian.reply()`'s tool list, and requires the `reply()` signature already includes `session_id` (fixed in Plan 1's implementation plan on 2026-07-09, before Plan 1 was executed).

## Global Constraints

- The next migration revision is `0012` (heads: `0001`→...→`0010`→`0011`). If Plan 1 hasn't merged by the time this is implemented, renumber to whatever comes after Plan 1's actual migration.
- No DB `CHECK` constraints — `item_type`, `status` on `custodian_logged_items`, and `target_type` on `importance_signals` are validated in Python, matching every other enum-like column in this codebase.
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod.
- All repository methods take an already-open `AsyncConnection` via `BaseRepository.__init__`; RLS scoping happens implicitly through `kernel/db/session.py`'s `session(user_id)` context manager.
- Orchestration (multi-repo composition, business rules) lives in a pure `kernel/` module with no FastAPI/dramatiq dependency — the API layer only translates a raised exception's `reason` into an HTTP status, mirroring `kernel/concepts_promotion.py`'s `approve_candidate`/`CandidateNotPromotable` shape exactly.
- `notes` and `importance_signals` are append-only in v1 — no update/delete methods.
- Design reference: `docs/superpowers/specs/2026-07-09-custodian-logging-design.md`.

---

### Task 1: Migration, models, and repositories

**Files:**
- Create: `migrations/versions/0012_custodian_logging.py`
- Modify: `kernel/models.py` (add `CustodianLoggedItem`, `Note`, `ImportanceSignal`)
- Create: `kernel/db/custodian_logged_items.py`
- Create: `kernel/db/notes.py`
- Create: `kernel/db/importance_signals.py`
- Modify: `kernel/db/claims.py` (add `set_assertion_type`)
- Modify: `kernel/db/sources.py` (add `get_by_type`)
- Modify: `kernel/db/observations.py` (make `bulk_insert`'s `source_id` nullable)
- Modify: `kernel/ingestion/base.py` (add `SourceType.CUSTODIAN`, but do **not** add it to `SourceType.ALL` — see Step 7)
- Create: `tests/kernel/test_custodian_logged_items_repository.py`
- Create: `tests/kernel/test_notes_repository.py`
- Create: `tests/kernel/test_importance_signals_repository.py`
- Modify: `tests/kernel/test_claims_repository.py` (add a `set_assertion_type` case)
- Modify: `tests/kernel/test_sources_repository.py` (add a `get_by_type` case)
- Modify: `tests/kernel/test_tenant_isolation.py` (add a Custodian Logging isolation case)
- Modify: `tests/conftest.py` and `tests/backend/conftest.py` (teardown for the 3 new tables)

**Interfaces:**
- Produces: `CustodianLoggedItem` (`id, user_id, session_id, message_id, item_type, target_id, content, status, created_at, resolved_at`); `Note` (`id, user_id, content, created_at`); `ImportanceSignal` (`id, user_id, target_type, target_id, created_at`); `ITEM_TYPES`, `STATUSES` (in `kernel/db/custodian_logged_items.py`); `IMPORTANCE_TARGET_TYPES` (in `kernel/db/importance_signals.py`); `CustodianLoggedItemRepository(conn)` with `create(*, user_id, session_id, item_type, content, target_id=None, message_id=None) -> CustodianLoggedItem`, `get(item_id) -> CustodianLoggedItem | None`, `list_for_session(session_id) -> list[CustodianLoggedItem]`, `resolve(item_id, status, *, target_id=None) -> CustodianLoggedItem | None`, `set_message_id(item_id, message_id) -> None`; `NoteRepository(conn).create(*, user_id, content) -> Note`; `ImportanceSignalRepository(conn).create(*, user_id, target_type, target_id) -> ImportanceSignal`; `ClaimRepository.set_assertion_type(claim_id, assertion_type) -> Claim | None`; `SourceRepository.get_by_type(source_type) -> Source | None`; `ObservationRepository.bulk_insert(rows, source_id: str | UUID | None, user_id) -> list[UUID]`.
- Consumes: `kernel/db/base_repository.py`'s `BaseRepository`/`strip_nul_bytes`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0012_custodian_logging.py`:

```python
"""custodian logging — proposed-item workflow, notes, importance signals

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-09
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

DATA_TABLES = ["custodian_logged_items", "notes", "importance_signals"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custodian_logged_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            session_id UUID NOT NULL REFERENCES custodian_sessions(id),
            message_id UUID REFERENCES custodian_messages(id),
            item_type TEXT NOT NULL,
            target_id UUID,
            content JSONB NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE importance_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            target_type TEXT NOT NULL,
            target_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX custodian_logged_items_session_idx ON custodian_logged_items "
        "(session_id, created_at)"
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
    op.execute("DROP TABLE IF EXISTS custodian_logged_items CASCADE")
    op.execute("DROP TABLE IF EXISTS notes CASCADE")
    op.execute("DROP TABLE IF EXISTS importance_signals CASCADE")
```

- [ ] **Step 2: Run the migration**

Run: `alembic upgrade head`
Expected: no errors; `alembic current` shows `0012`.

- [ ] **Step 3: Add the models**

In `kernel/models.py`, after the `Revision` class, add:

```python
@dataclass(frozen=True, slots=True)
class CustodianLoggedItem:
    id: UUID
    user_id: UUID
    session_id: UUID
    item_type: str
    content: Mapping[str, Any]
    status: str
    created_at: datetime
    message_id: UUID | None = None
    target_id: UUID | None = None
    resolved_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianLoggedItem:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            item_type=row["item_type"],
            content=row["content"],
            status=row["status"],
            created_at=row["created_at"],
            message_id=row.get("message_id"),
            target_id=row.get("target_id"),
            resolved_at=row.get("resolved_at"),
        )


@dataclass(frozen=True, slots=True)
class Note:
    id: UUID
    user_id: UUID
    content: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Note:
        return cls(
            id=row["id"], user_id=row["user_id"], content=row["content"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ImportanceSignal:
    id: UUID
    user_id: UUID
    target_type: str
    target_id: UUID
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ImportanceSignal:
        return cls(
            id=row["id"], user_id=row["user_id"], target_type=row["target_type"],
            target_id=row["target_id"], created_at=row["created_at"],
        )
```

- [ ] **Step 4: Write the CustodianLoggedItem repository**

Create `kernel/db/custodian_logged_items.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import CustodianLoggedItem

ITEM_TYPES = {
    "observation",
    "note",
    "claim",
    "task",
    "concept_candidate",
    "reality_assertion",
    "perception_assertion",
    "contradiction",
    "importance_signal",
}
STATUSES = {"proposed", "accepted", "rejected", "superseded"}

_COLUMNS = (
    "id, user_id, session_id, message_id, item_type, target_id, content, "
    "status, created_at, resolved_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class CustodianLoggedItemRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        session_id: str | UUID,
        item_type: str,
        content: dict[str, Any],
        target_id: str | UUID | None = None,
        message_id: str | UUID | None = None,
    ) -> CustodianLoggedItem:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_logged_items
                        (user_id, session_id, message_id, item_type, target_id, content)
                    VALUES
                        (:user_id, :session_id, :message_id, :item_type, :target_id,
                         CAST(:content AS JSONB))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "session_id": str(session_id),
                    "message_id": str(message_id) if message_id else None,
                    "item_type": item_type,
                    "target_id": str(target_id) if target_id else None,
                    "content": json.dumps(strip_nul_bytes(content)),
                },
            )
        ).mappings().one()
        return CustodianLoggedItem.from_row(_as_mapping(row))

    async def get(self, item_id: str | UUID) -> CustodianLoggedItem | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM custodian_logged_items WHERE id = :id"),
                {"id": str(item_id)},
            )
        ).mappings().first()
        return CustodianLoggedItem.from_row(_as_mapping(row)) if row else None

    async def list_for_session(self, session_id: str | UUID) -> list[CustodianLoggedItem]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM custodian_logged_items "
                    "WHERE session_id = :session_id ORDER BY created_at ASC"
                ),
                {"session_id": str(session_id)},
            )
        ).mappings().all()
        return [CustodianLoggedItem.from_row(_as_mapping(r)) for r in rows]

    async def resolve(
        self, item_id: str | UUID, status: str, *, target_id: str | UUID | None = None
    ) -> CustodianLoggedItem | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE custodian_logged_items
                    SET status = :status, resolved_at = now(),
                        target_id = COALESCE(:target_id, target_id)
                    WHERE id = :id AND status = 'proposed'
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "id": str(item_id),
                    "status": status,
                    "target_id": str(target_id) if target_id else None,
                },
            )
        ).mappings().first()
        return CustodianLoggedItem.from_row(_as_mapping(row)) if row else None

    async def set_message_id(self, item_id: str | UUID, message_id: str | UUID) -> None:
        await self.conn.execute(
            text("UPDATE custodian_logged_items SET message_id = :message_id WHERE id = :id"),
            {"id": str(item_id), "message_id": str(message_id)},
        )
```

- [ ] **Step 5: Write the Note and ImportanceSignal repositories**

Create `kernel/db/notes.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Note

_COLUMNS = "id, user_id, content, created_at"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class NoteRepository(BaseRepository):
    async def create(self, *, user_id: str | UUID, content: str) -> Note:
        row = (
            await self.conn.execute(
                text(
                    f"INSERT INTO notes (user_id, content) VALUES (:user_id, :content) "
                    f"RETURNING {_COLUMNS}"
                ),
                {"user_id": str(user_id), "content": strip_nul_bytes(content)},
            )
        ).mappings().one()
        return Note.from_row(_as_mapping(row))

    async def get(self, note_id: str | UUID) -> Note | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM notes WHERE id = :id"), {"id": str(note_id)}
            )
        ).mappings().first()
        return Note.from_row(_as_mapping(row)) if row else None

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[Note]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM notes ORDER BY created_at DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Note.from_row(_as_mapping(r)) for r in rows]
```

Create `kernel/db/importance_signals.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import ImportanceSignal

IMPORTANCE_TARGET_TYPES = {"claim", "concept", "observation"}

_COLUMNS = "id, user_id, target_type, target_id, created_at"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ImportanceSignalRepository(BaseRepository):
    async def create(
        self, *, user_id: str | UUID, target_type: str, target_id: str | UUID
    ) -> ImportanceSignal:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO importance_signals (user_id, target_type, target_id)
                    VALUES (:user_id, :target_type, :target_id)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "target_type": target_type,
                    "target_id": str(target_id),
                },
            )
        ).mappings().one()
        return ImportanceSignal.from_row(_as_mapping(row))

    async def list_for_target(
        self, target_type: str, target_id: str | UUID
    ) -> list[ImportanceSignal]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM importance_signals "
                    "WHERE target_type = :target_type AND target_id = :target_id "
                    "ORDER BY created_at DESC"
                ),
                {"target_type": target_type, "target_id": str(target_id)},
            )
        ).mappings().all()
        return [ImportanceSignal.from_row(_as_mapping(r)) for r in rows]
```

- [ ] **Step 6: Add `set_assertion_type` and `get_by_type`**

In `kernel/db/claims.py`, add (check the file's `_COLUMNS` constant name at the top before writing this — it's the same constant already used by `create`/`get`):

```python
    async def set_assertion_type(
        self, claim_id: str | UUID, assertion_type: str
    ) -> Claim | None:
        row = (
            await self.conn.execute(
                text(
                    f"UPDATE claims SET assertion_type = :assertion_type WHERE id = :id "
                    f"RETURNING {_COLUMNS}"
                ),
                {"id": str(claim_id), "assertion_type": assertion_type},
            )
        ).mappings().first()
        return Claim.from_row(_as_mapping(row)) if row else None
```

In `kernel/db/sources.py`, add:

```python
    async def get_by_type(self, source_type: str) -> Source | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM sources WHERE source_type = :t LIMIT 1"),
                {"t": source_type},
            )
        ).mappings().first()
        return Source.from_row(_as_mapping(row)) if row else None
```

- [ ] **Step 7: Add the `custodian` source type — display-only, not upload-eligible**

In `kernel/ingestion/base.py`, add `CUSTODIAN` as a class attribute but **do not** add it to `SourceType.ALL`:

```python
class SourceType:
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    CHATGPT = "chatgpt"
    META = "meta"
    CUSTODIAN = "custodian"
    ALL: tuple[str, ...] = (JSON, MARKDOWN, HTML, PDF, CHATGPT, META)
```

`ALL` is what `backend/app/api/sources.py`'s upload endpoint validates against (`if source_type not in SourceType.ALL: raise HTTPException(400, ...)`) and what `get_parser(source_type)` dispatches on — a `custodian` source is never uploaded or parsed, it's created directly by `kernel/custodian_logging.py` (Task 2), so it must stay out of `ALL` to avoid a user being able to select it in the upload form and hit a missing-parser error.

- [ ] **Step 8: Make `bulk_insert`'s `source_id` nullable**

In `kernel/db/observations.py`, change the `bulk_insert` signature and the one line that stringifies `source_id`:

```python
    async def bulk_insert(
        self, rows: list[dict[str, Any]], source_id: str | UUID | None, user_id: str | UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for row in rows:
            new_id = (
                await self.conn.execute(
                    text(
                        """
                        INSERT INTO observations
                            (user_id, source_id, fragment_id, observed_at, speaker,
                             content, context_before, context_after, confidence)
                        VALUES (:user_id, :source_id, :fragment_id, :observed_at, :speaker,
                                :content, :ctx_before, :ctx_after, :confidence)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "source_id": str(source_id) if source_id is not None else None,
                        "fragment_id": row.get("fragment_id"),
                        "observed_at": row.get("observed_at"),
                        "speaker": row.get("speaker"),
                        "content": row["content"],
                        "ctx_before": row.get("context_before"),
                        "ctx_after": row.get("context_after"),
                        "confidence": row.get("confidence", 1.0),
                    },
                )
            ).scalar_one()
            ids.append(new_id)
        return ids
```

(Every existing call site already passes a real source id, so this change is additive-only — it doesn't affect any existing caller.)

- [ ] **Step 9: Write the failing repository tests**

Create `tests/kernel/test_custodian_logged_items_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.custodian import CustodianRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.session import session


async def _make_session(conn, user_id):  # type: ignore[no-untyped-def]
    return await CustodianRepository(conn).create_session(
        user_id=user_id, model="gpt-4o-mini", provider="openai"
    )


@pytest.mark.asyncio
async def test_create_and_get_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id,
            session_id=custodian_session.id,
            item_type="note",
            content={"content": "Remember this."},
        )
        fetched = await repo.get(created.id)

    assert created.status == "proposed"
    assert created.target_id is None
    assert created.message_id is None
    assert fetched == created


@pytest.mark.asyncio
async def test_list_for_session_orders_oldest_first(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        first = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "first"},
        )
        second = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "second"},
        )
        listed = await repo.list_for_session(custodian_session.id)

    assert [i.id for i in listed] == [first.id, second.id]


@pytest.mark.asyncio
async def test_resolve_only_transitions_proposed_items(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "x"},
        )
        accepted = await repo.resolve(created.id, "accepted")
        already_resolved = await repo.resolve(created.id, "rejected")

    assert accepted is not None
    assert accepted.status == "accepted"
    assert accepted.resolved_at is not None
    assert already_resolved is None


@pytest.mark.asyncio
async def test_resolve_sets_target_id_when_given(make_user):
    from uuid import uuid4

    user_id = await make_user()
    new_id = uuid4()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="observation",
            content={"content": "x"},
        )
        resolved = await repo.resolve(created.id, "accepted", target_id=new_id)

    assert resolved is not None
    assert resolved.target_id == new_id


@pytest.mark.asyncio
async def test_set_message_id_backfills(make_user):
    from uuid import uuid4

    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "x"},
        )
        message_id = uuid4()
        await repo.set_message_id(created.id, message_id)
        fetched = await repo.get(created.id)

    assert fetched is not None
    assert fetched.message_id == message_id
```

Create `tests/kernel/test_notes_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.notes import NoteRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_list_notes(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = NoteRepository(conn)
        created = await repo.create(user_id=user_id, content="Remember to check the archive.")
        listed = await repo.list()

    assert created.content == "Remember to check the archive."
    assert [n.id for n in listed] == [created.id]
```

Create `tests/kernel/test_importance_signals_repository.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest

from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_list_for_target(make_user):
    user_id = await make_user()
    target_id = uuid4()
    async with session(user_id) as conn:
        repo = ImportanceSignalRepository(conn)
        created = await repo.create(user_id=user_id, target_type="claim", target_id=target_id)
        listed = await repo.list_for_target("claim", target_id)

    assert created.target_type == "claim"
    assert [s.id for s in listed] == [created.id]
```

In `tests/kernel/test_claims_repository.py`, add:

```python
@pytest.mark.asyncio
async def test_set_assertion_type_updates_the_claim(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "set-assertion-type-1")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "It rained."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id, source_id=source.id, observation_id=obs_id,
            claim_text="It rained.", claim_type="fact", assertion_type="interpretation",
            confidence=0.9, extraction_method="test", model_name="fake", prompt_version="v1",
        )
        assert claim is not None
        updated = await ClaimRepository(conn).set_assertion_type(claim.id, "perception")

    assert updated is not None
    assert updated.assertion_type == "perception"
```

(Check the top of `tests/kernel/test_claims_repository.py` for its existing imports — `SourceRepository`, `ObservationRepository`, `ClaimRepository`, `session`, `pytest` should already be there.)

In `tests/kernel/test_sources_repository.py`, add:

```python
@pytest.mark.asyncio
async def test_get_by_type_finds_a_matching_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        await repo.create(user_id, "json", "get-by-type-1")
        custodian_source = await repo.create(user_id, "custodian", "get-by-type-2")
        found = await repo.get_by_type("custodian")

    assert found is not None
    assert found.id == custodian_source.id
```

- [ ] **Step 10: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_logged_items_repository.py tests/kernel/test_notes_repository.py tests/kernel/test_importance_signals_repository.py -v`
Expected: FAIL — `ModuleNotFoundError` for the three new modules.

- [ ] **Step 11: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_logged_items_repository.py tests/kernel/test_notes_repository.py tests/kernel/test_importance_signals_repository.py tests/kernel/test_claims_repository.py tests/kernel/test_sources_repository.py -v`
Expected: all pass.

- [ ] **Step 12: Add tenant isolation coverage**

In `tests/kernel/test_tenant_isolation.py`, add:

```python
@pytest.mark.asyncio
async def test_custodian_logged_items_isolated_between_tenants(make_user):
    from kernel.db.custodian import CustodianRepository
    from kernel.db.custodian_logged_items import CustodianLoggedItemRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_a, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=user_a, session_id=custodian_session.id, item_type="note",
            content={"content": "Secret note."},
        )

    async with session(user_b) as conn:
        assert await CustodianLoggedItemRepository(conn).get(item.id) is None
        assert await CustodianLoggedItemRepository(conn).list_for_session(
            custodian_session.id
        ) == []
```

Run: `pytest tests/kernel/test_tenant_isolation.py -v`
Expected: all pass.

- [ ] **Step 13: Add teardown cleanup**

In `tests/conftest.py`'s `make_user` teardown, add before the existing `DELETE FROM custodian_messages`:

```python
            await conn.execute(text("DELETE FROM custodian_logged_items"))
            await conn.execute(text("DELETE FROM notes"))
            await conn.execute(text("DELETE FROM importance_signals"))
```

Apply the equivalent additions to `tests/backend/conftest.py`'s `seeded_user` cleanup blocks (both the `MIGRATION_DATABASE_URL`-scoped block and the RLS-scoped one), matching the exact pattern used there for `custodian_messages`/`custodian_sessions` from Plan 1.

Run: `pytest tests/kernel/ tests/backend/ -v`
Expected: all pass, no leftover-row failures across test runs.

- [ ] **Step 14: Commit**

```bash
git add migrations/versions/0012_custodian_logging.py kernel/models.py \
  kernel/db/custodian_logged_items.py kernel/db/notes.py kernel/db/importance_signals.py \
  kernel/db/claims.py kernel/db/sources.py kernel/db/observations.py kernel/ingestion/base.py \
  tests/kernel/test_custodian_logged_items_repository.py tests/kernel/test_notes_repository.py \
  tests/kernel/test_importance_signals_repository.py tests/kernel/test_claims_repository.py \
  tests/kernel/test_sources_repository.py tests/kernel/test_tenant_isolation.py \
  tests/conftest.py tests/backend/conftest.py
git commit -m "feat: add custodian_logged_items/notes/importance_signals tables and repositories"
```

---

### Task 2: Accept/reject orchestration

**Files:**
- Create: `kernel/custodian_logging.py`
- Create: `tests/kernel/test_custodian_logging.py`

**Interfaces:**
- Produces: `LoggedItemNotResolvable(message, reason)` exception (`reason` is one of `"not_found"`, `"invalid_status"`, `"concept_mismatch"`, `"duplicate"`); `get_or_create_custodian_source(conn, user_id) -> Source`; `accept_logged_item(conn, item_id) -> CustodianLoggedItem`; `reject_logged_item(conn, item_id) -> CustodianLoggedItem`.
- Consumes: `kernel.db.custodian_logged_items.CustodianLoggedItemRepository` (Task 1), `kernel.db.notes.NoteRepository`, `kernel.db.importance_signals.ImportanceSignalRepository`, `kernel.db.claims.ClaimRepository`, `kernel.db.claim_concept_edges.ClaimConceptEdgeRepository`, `kernel.db.concept_candidates.ConceptCandidateRepository`, `kernel.db.contradictions.ContradictionRepository`, `kernel.db.observations.ObservationRepository`, `kernel.db.sources.SourceRepository`, `kernel.ingestion.base.SourceType`.

- [ ] **Step 1: Write the module**

Create `kernel/custodian_logging.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.notes import NoteRepository
from kernel.db.observations import ObservationRepository
from kernel.db.sources import SourceRepository
from kernel.ingestion.base import SourceType
from kernel.models import CustodianLoggedItem, Source


@dataclass
class LoggedItemNotResolvable(Exception):
    """Raised when a logged item can't be accepted/rejected: missing,
    invisible to this tenant (RLS), already resolved, or (contradiction
    proposals only) the two claims aren't both linked to the stated concept
    yet. The API layer catches this to decide the HTTP status."""

    message: str
    reason: str  # "not_found" | "invalid_status" | "concept_mismatch" | "duplicate"


async def get_or_create_custodian_source(conn: AsyncConnection, user_id: str | UUID) -> Source:
    """One verified 'custodian'-type Source per user, created lazily and
    reused — lets Custodian-created claims satisfy claims.source_id's
    NOT NULL FK without a parallel ingestion pipeline. See
    kernel/ingestion/base.py: this type is deliberately excluded from
    SourceType.ALL (never uploaded, never parsed)."""
    sources = SourceRepository(conn)
    existing = await sources.get_by_type(SourceType.CUSTODIAN)
    if existing is not None:
        return existing
    source = await sources.create(user_id, SourceType.CUSTODIAN, "custodian-source")
    await sources.mark_verified(source.id)
    return source


async def _get_or_raise(
    items: CustodianLoggedItemRepository, item_id: str | UUID
) -> CustodianLoggedItem:
    item = await items.get(item_id)
    if item is None:
        raise LoggedItemNotResolvable(
            message=f"logged item {item_id} not found", reason="not_found"
        )
    if item.status != "proposed":
        raise LoggedItemNotResolvable(
            message=f"logged item {item_id} has status {item.status!r}, expected 'proposed'",
            reason="invalid_status",
        )
    return item


async def accept_logged_item(conn: AsyncConnection, item_id: str | UUID) -> CustodianLoggedItem:
    items = CustodianLoggedItemRepository(conn)
    item = await _get_or_raise(items, item_id)
    new_target_id: UUID | None = None

    if item.item_type == "observation":
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [
                {
                    "content": item.content["content"],
                    "speaker": item.content.get("speaker"),
                    "observed_at": item.content.get("observed_at"),
                }
            ],
            None,
            item.user_id,
        )
        new_target_id = obs_id

    elif item.item_type == "note":
        note = await NoteRepository(conn).create(
            user_id=item.user_id, content=item.content["content"]
        )
        new_target_id = note.id

    elif item.item_type in ("claim", "task"):
        source = await get_or_create_custodian_source(conn, item.user_id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": item.content["claim_text"]}], source.id, item.user_id
        )
        claim_type = "task" if item.item_type == "task" else item.content["claim_type"]
        assertion_type = (
            "reality" if item.item_type == "task" else item.content["assertion_type"]
        )
        claim = await ClaimRepository(conn).create(
            user_id=item.user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text=item.content["claim_text"],
            claim_type=claim_type,
            assertion_type=assertion_type,
            confidence=1.0,
            extraction_method="custodian",
            model_name=None,
            prompt_version=None,
        )
        if claim is None:
            raise LoggedItemNotResolvable(message="claim already exists", reason="duplicate")
        new_target_id = claim.id

    elif item.item_type == "concept_candidate":
        claim = await ClaimRepository(conn).get(item.target_id)
        if claim is None:
            raise LoggedItemNotResolvable(message="target claim not found", reason="not_found")
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=item.user_id,
            source_id=claim.source_id,
            claim_id=claim.id,
            candidate_name=item.content["candidate_name"],
            concept_type=item.content["concept_type"],
            rationale=item.content.get("rationale"),
            confidence=1.0,
            extraction_method="custodian",
            model_name=None,
            prompt_version=None,
        )
        new_target_id = candidate.id

    elif item.item_type in ("reality_assertion", "perception_assertion"):
        assertion_type = "reality" if item.item_type == "reality_assertion" else "perception"
        updated = await ClaimRepository(conn).set_assertion_type(item.target_id, assertion_type)
        if updated is None:
            raise LoggedItemNotResolvable(message="target claim not found", reason="not_found")

    elif item.item_type == "contradiction":
        edges = ClaimConceptEdgeRepository(conn)
        concept_id = item.content["concept_id"]
        claim_b_id = item.content["claim_b_id"]
        a_concepts = {str(e.concept_id) for e in await edges.list_for_claim(item.target_id)}
        b_concepts = {str(e.concept_id) for e in await edges.list_for_claim(claim_b_id)}
        if concept_id not in a_concepts or concept_id not in b_concepts:
            raise LoggedItemNotResolvable(
                message="both claims must already be linked to the given concept",
                reason="concept_mismatch",
            )
        contradiction = await ContradictionRepository(conn).create(
            user_id=item.user_id,
            concept_id=concept_id,
            claim_a_id=item.target_id,
            claim_b_id=claim_b_id,
            similarity=1.0,
            rationale=item.content.get("rationale", ""),
        )
        if contradiction is None:
            raise LoggedItemNotResolvable(
                message="contradiction already exists", reason="duplicate"
            )
        new_target_id = contradiction.id

    elif item.item_type == "importance_signal":
        signal = await ImportanceSignalRepository(conn).create(
            user_id=item.user_id,
            target_type=item.content["target_type"],
            target_id=item.target_id,
        )
        new_target_id = signal.id

    resolved = await items.resolve(item_id, "accepted", target_id=new_target_id)
    assert resolved is not None, "item was 'proposed' one line above — resolve cannot race here"
    return resolved


async def reject_logged_item(conn: AsyncConnection, item_id: str | UUID) -> CustodianLoggedItem:
    items = CustodianLoggedItemRepository(conn)
    await _get_or_raise(items, item_id)
    resolved = await items.resolve(item_id, "rejected")
    assert resolved is not None, "item was 'proposed' one line above — resolve cannot race here"
    return resolved
```

- [ ] **Step 2: Write the failing tests**

Create `tests/kernel/test_custodian_logging.py`:

```python
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
```

Check `ObservationRepository`'s `list` method signature before running this (used in the first test) — it should already support a bare `limit=` call per its existing usage elsewhere in this codebase.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_logging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kernel.custodian_logging'`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_logging.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add kernel/custodian_logging.py tests/kernel/test_custodian_logging.py
git commit -m "feat: add Custodian Logging accept/reject orchestration"
```

---

### Task 3: Propose tools in the conversation engine

**Files:**
- Modify: `kernel/ai/custodian.py` (add 9 `propose_*` tools + dispatch)
- Modify: `tests/kernel/test_custodian_engine.py` (add cases for the new tools)

**Interfaces:**
- Produces: nine new tool constants (`PROPOSE_OBSERVATION_TOOL`, `PROPOSE_NOTE_TOOL`, `PROPOSE_CLAIM_TOOL`, `PROPOSE_TASK_TOOL`, `PROPOSE_CONCEPT_CANDIDATE_TOOL`, `PROPOSE_REALITY_ASSERTION_TOOL`, `PROPOSE_PERCEPTION_ASSERTION_TOOL`, `PROPOSE_CONTRADICTION_TOOL`, `PROPOSE_IMPORTANCE_SIGNAL_TOOL`); `OpenAICustodian.reply(...)`'s tool list grows to 11 and its dispatch grows to route these 9 new tool names to `CustodianLoggedItemRepository.create(...)`, returning `json.dumps({"proposal_id": str(item.id), "status": "proposed"})` as the tool output.
- Consumes: `kernel.db.custodian_logged_items.CustodianLoggedItemRepository`, `ITEM_TYPES` (Task 1); `kernel.ai.claim_extraction.CLAIM_TYPES`, `ASSERTION_TYPES`, `CONCEPT_TYPES`; `kernel.db.importance_signals.IMPORTANCE_TARGET_TYPES` (Task 1).

- [ ] **Step 1: Add the tool schemas**

In `kernel/ai/custodian.py`, add after `SEARCH_CONCEPTS_TOOL` (import `CLAIM_TYPES`, `ASSERTION_TYPES`, `CONCEPT_TYPES` from `kernel.ai.claim_extraction`, and `IMPORTANCE_TARGET_TYPES` from `kernel.db.importance_signals` at the top of the file):

```python
from kernel.ai.claim_extraction import ASSERTION_TYPES, CLAIM_TYPES, CONCEPT_TYPES
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.importance_signals import IMPORTANCE_TARGET_TYPES

_PROPOSABLE_CLAIM_TYPES = sorted(CLAIM_TYPES - {"task"})

PROPOSE_OBSERVATION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_observation",
    "description": (
        "Propose logging this as a new observation in the archive. The user "
        "must explicitly accept before it becomes real — this only suggests it."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["content", "speaker", "observed_at"],
        "properties": {
            "content": {"type": "string"},
            "speaker": {"type": ["string", "null"]},
            "observed_at": {
                "type": ["string", "null"],
                "description": "ISO 8601 timestamp, or null if unknown.",
            },
        },
    },
}

PROPOSE_NOTE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_note",
    "description": "Propose saving this as a freestanding note. Requires user acceptance.",
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["content"],
        "properties": {"content": {"type": "string"}},
    },
}

PROPOSE_CLAIM_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_claim",
    "description": (
        "Propose logging this as a new claim (an atomic statement). Requires "
        "user acceptance. Use propose_task instead if this is an action item."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_text", "claim_type", "assertion_type"],
        "properties": {
            "claim_text": {"type": "string"},
            "claim_type": {"type": "string", "enum": _PROPOSABLE_CLAIM_TYPES},
            "assertion_type": {"type": "string", "enum": sorted(ASSERTION_TYPES)},
        },
    },
}

PROPOSE_TASK_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_task",
    "description": "Propose logging this as a task (an action item). Requires user acceptance.",
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_text"],
        "properties": {"claim_text": {"type": "string"}},
    },
}

PROPOSE_CONCEPT_CANDIDATE_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_concept_candidate",
    "description": (
        "Propose that an existing claim (found via search_archive, or one "
        "just logged in this conversation) relates to a concept. Requires "
        "user acceptance — this is the same review step as any other "
        "concept candidate."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_id", "candidate_name", "concept_type", "rationale"],
        "properties": {
            "claim_id": {"type": "string"},
            "candidate_name": {"type": "string"},
            "concept_type": {"type": "string", "enum": sorted(CONCEPT_TYPES)},
            "rationale": {"type": ["string", "null"]},
        },
    },
}

PROPOSE_REALITY_ASSERTION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_reality_assertion",
    "description": (
        "Propose re-tagging an existing claim as describing objective reality, "
        "not perception or interpretation. Requires user acceptance."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_id"],
        "properties": {"claim_id": {"type": "string"}},
    },
}

PROPOSE_PERCEPTION_ASSERTION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_perception_assertion",
    "description": (
        "Propose re-tagging an existing claim as describing a perception, "
        "not objective reality. Requires user acceptance."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_id"],
        "properties": {"claim_id": {"type": "string"}},
    },
}

PROPOSE_CONTRADICTION_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_contradiction",
    "description": (
        "Propose that two existing claims, both already linked to the same "
        "concept, contradict each other. Requires user acceptance."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claim_a_id", "claim_b_id", "concept_id", "rationale"],
        "properties": {
            "claim_a_id": {"type": "string"},
            "claim_b_id": {"type": "string"},
            "concept_id": {"type": "string"},
            "rationale": {"type": "string"},
        },
    },
}

PROPOSE_IMPORTANCE_SIGNAL_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "propose_importance_signal",
    "description": (
        "Propose pinning an existing claim, concept, or observation as "
        "important. Requires user acceptance."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_type", "target_id"],
        "properties": {
            "target_type": {"type": "string", "enum": sorted(IMPORTANCE_TARGET_TYPES)},
            "target_id": {"type": "string"},
        },
    },
}

_PROPOSE_TOOLS = (
    PROPOSE_OBSERVATION_TOOL,
    PROPOSE_NOTE_TOOL,
    PROPOSE_CLAIM_TOOL,
    PROPOSE_TASK_TOOL,
    PROPOSE_CONCEPT_CANDIDATE_TOOL,
    PROPOSE_REALITY_ASSERTION_TOOL,
    PROPOSE_PERCEPTION_ASSERTION_TOOL,
    PROPOSE_CONTRADICTION_TOOL,
    PROPOSE_IMPORTANCE_SIGNAL_TOOL,
)

# Maps a propose_* tool name to (item_type, target_field | None). target_field
# names the arg holding the existing row this proposal acts on — None for the
# five freestanding-create types, whose target_id stays null until accepted.
_PROPOSE_TOOL_ITEM_TYPES: dict[str, tuple[str, str | None]] = {
    "propose_observation": ("observation", None),
    "propose_note": ("note", None),
    "propose_claim": ("claim", None),
    "propose_task": ("task", None),
    "propose_concept_candidate": ("concept_candidate", "claim_id"),
    "propose_reality_assertion": ("reality_assertion", "claim_id"),
    "propose_perception_assertion": ("perception_assertion", "claim_id"),
    "propose_contradiction": ("contradiction", "claim_a_id"),
    "propose_importance_signal": ("importance_signal", "target_id"),
}
```

- [ ] **Step 2: Add the propose-tool executor and wire it into the dispatch**

Still in `kernel/ai/custodian.py`, add the executor function near `_run_search_concepts`:

```python
async def _run_propose_tool(
    conn: Any, user_id: str | UUID, session_id: str | UUID, tool_name: str, args: dict[str, Any]
) -> str:
    item_type, target_field = _PROPOSE_TOOL_ITEM_TYPES[tool_name]
    target_id = args.pop(target_field) if target_field else None
    item = await CustodianLoggedItemRepository(conn).create(
        user_id=user_id, session_id=session_id, item_type=item_type, content=args,
        target_id=target_id,
    )
    return json.dumps({"proposal_id": str(item.id), "status": "proposed"})
```

Update `OpenAICustodian.reply`'s tool list (`tools=[SEARCH_ARCHIVE_TOOL, SEARCH_CONCEPTS_TOOL]`) to:

```python
                tools=[SEARCH_ARCHIVE_TOOL, SEARCH_CONCEPTS_TOOL, *_PROPOSE_TOOLS],
```

and extend the dispatch `if/elif` chain (currently `search_archive` / `search_concepts` / `else: unknown`) to:

```python
                if call.name == "search_archive":
                    output = await _run_search_archive(conn, args["query"], args["limit"])
                elif call.name == "search_concepts":
                    output = await _run_search_concepts(conn, args["query"], args["limit"])
                elif call.name in _PROPOSE_TOOL_ITEM_TYPES:
                    output = await _run_propose_tool(conn, user_id, session_id, call.name, args)
                else:
                    output = json.dumps({"error": f"unknown tool {call.name}"})
```

(`session_id` is already a parameter of `reply()` since Plan 1's fix — no further signature change needed here.)

- [ ] **Step 3: Write the failing tests**

In `tests/kernel/test_custodian_engine.py`, add:

```python
@pytest.mark.asyncio
async def test_reply_executes_propose_note_tool(make_user):
    user_id = await make_user()
    call_args = json.dumps({"content": "Remember this."})
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse("resp_1", [_FunctionCall("call_1", "propose_note", call_args)]),
            ),
            ([_Delta("Noted, want me to save it?")], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        from kernel.db.custodian import CustodianRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        tool_calls: list[ToolCallRecord] = []

        async def on_token(delta: str) -> None:
            pass

        async def on_tool_call(record: ToolCallRecord) -> None:
            tool_calls.append(record)

        reply = await custodian.reply(
            conn, user_id, custodian_session.id, [{"role": "user", "content": "log this"}],
            on_token, on_tool_call,
        )
        proposal_id = json.loads(tool_calls[0].tool_output)["proposal_id"]

        from kernel.db.custodian_logged_items import CustodianLoggedItemRepository

        item = await CustodianLoggedItemRepository(conn).get(proposal_id)

    assert reply.content == "Noted, want me to save it?"
    assert item is not None
    assert item.item_type == "note"
    assert item.status == "proposed"
    assert item.content == {"content": "Remember this."}


@pytest.mark.asyncio
async def test_reply_executes_propose_reality_assertion_tool_with_target_id(make_user):
    user_id = await make_user()
    from uuid import uuid4

    claim_id = uuid4()
    call_args = json.dumps({"claim_id": str(claim_id)})
    fake_client = FakeOpenAIClient(
        [
            (
                [],
                _FakeResponse(
                    "resp_1",
                    [_FunctionCall("call_1", "propose_reality_assertion", call_args)],
                ),
            ),
            ([], _FakeResponse("resp_2", [])),
        ]
    )
    custodian = OpenAICustodian(api_key="x", model="gpt-4o-mini", client=fake_client)

    async with session(user_id) as conn:
        from kernel.db.custodian import CustodianRepository
        from kernel.db.custodian_logged_items import CustodianLoggedItemRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        tool_calls: list[ToolCallRecord] = []

        async def on_token(delta: str) -> None:
            pass

        async def on_tool_call(record: ToolCallRecord) -> None:
            tool_calls.append(record)

        await custodian.reply(
            conn, user_id, custodian_session.id, [{"role": "user", "content": "mark it"}],
            on_token, on_tool_call,
        )
        proposal_id = json.loads(tool_calls[0].tool_output)["proposal_id"]
        item = await CustodianLoggedItemRepository(conn).get(proposal_id)

    assert item is not None
    assert item.item_type == "reality_assertion"
    assert item.target_id == claim_id
    assert item.content == {}
```

These two tests create a real `custodian_session` row (via `CustodianRepository`) instead of reusing Plan 1's `_TEST_SESSION_ID` placeholder — `reply()` itself never validates that `session_id` refers to an existing row, but a `propose_*` tool's execution does a real `CustodianLoggedItemRepository.create(session_id=...)` insert, which has a `NOT NULL REFERENCES custodian_sessions(id)` FK, so the id must be real here. Plan 1's five existing tests keep using `_TEST_SESSION_ID` unchanged — they never execute a propose tool, so no FK is ever touched.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_custodian_engine.py -k propose -v`
Expected: FAIL — `AttributeError` or `KeyError` (tool names not yet recognized).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_custodian_engine.py -v`
Expected: all pass (7 total: the 5 from Plan 1 plus these 2).

- [ ] **Step 6: Commit**

```bash
git add kernel/ai/custodian.py tests/kernel/test_custodian_engine.py
git commit -m "feat: add 9 propose_* tools to the Custodian conversation engine"
```

---

### Task 4: Backend API

**Files:**
- Modify: `backend/app/api/custodian.py` (add list/accept/reject endpoints, backfill `message_id`)
- Modify: `tests/backend/test_custodian_api.py`

**Interfaces:**
- Produces: `GET /custodian/sessions/{id}/logged-items`, `POST /custodian/logged-items/{id}/accept`, `POST /custodian/logged-items/{id}/reject`.
- Consumes: `kernel.custodian_logging.accept_logged_item`/`reject_logged_item`/`LoggedItemNotResolvable` (Task 2), `kernel.db.custodian_logged_items.CustodianLoggedItemRepository` (Task 1).

- [ ] **Step 1: Add the endpoints and the message_id backfill**

In `backend/app/api/custodian.py`, add the imports:

```python
from kernel.custodian_logging import (
    LoggedItemNotResolvable,
    accept_logged_item,
    reject_logged_item,
)
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.models import CustodianLoggedItem
```

Add a serializer and the three endpoints:

```python
def _serialize_logged_item(item: CustodianLoggedItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "session_id": str(item.session_id),
        "item_type": item.item_type,
        "target_id": str(item.target_id) if item.target_id else None,
        "content": item.content,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }


_RESOLVE_STATUS_CODES = {
    "not_found": 404,
    "invalid_status": 409,
    "concept_mismatch": 422,
    "duplicate": 409,
}


@router.get("/custodian/sessions/{session_id}/logged-items")
async def list_logged_items(
    session_id: str, user_id: str = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        if await repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="not found")
        items = await CustodianLoggedItemRepository(conn).list_for_session(session_id)
    return [_serialize_logged_item(i) for i in items]


@router.post("/custodian/logged-items/{item_id}/accept")
async def accept_logged_item_endpoint(
    item_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            item = await accept_logged_item(conn, item_id)
        except LoggedItemNotResolvable as exc:
            raise HTTPException(
                status_code=_RESOLVE_STATUS_CODES[exc.reason], detail=exc.message
            ) from None
    return _serialize_logged_item(item)


@router.post("/custodian/logged-items/{item_id}/reject")
async def reject_logged_item_endpoint(
    item_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            item = await reject_logged_item(conn, item_id)
        except LoggedItemNotResolvable as exc:
            raise HTTPException(
                status_code=_RESOLVE_STATUS_CODES[exc.reason], detail=exc.message
            ) from None
    return _serialize_logged_item(item)
```

Now the `message_id` backfill: in `_generate_and_persist`, the existing loop that persists each `role="tool"` message (`for call in reply.tool_calls: await repo.add_message(...)`) already runs after `reply()` returns. Change it to capture the persisted message and, when the tool's output contains a `proposal_id`, backfill it:

```python
            for call in reply.tool_calls:
                message = await repo.add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="tool",
                    content="",
                    tool_name=call.tool_name,
                    tool_input=call.tool_input,
                    tool_output=call.tool_output,
                )
                try:
                    output = json.loads(call.tool_output)
                except json.JSONDecodeError:
                    output = {}
                proposal_id = output.get("proposal_id")
                if proposal_id:
                    await CustodianLoggedItemRepository(conn).set_message_id(
                        proposal_id, message.id
                    )
```

- [ ] **Step 2: Write the failing tests**

In `tests/backend/test_custodian_api.py`, add the imports (`from kernel.db.custodian_logged_items import CustodianLoggedItemRepository`, `from kernel.ai.custodian import ToolCallRecord` already imported) and:

```python
class FakeCustodianWithProposal:
    def __init__(self, proposal_tool_output: str) -> None:
        self._proposal_tool_output = proposal_tool_output

    async def reply(self, conn, user_id, session_id, history, on_token, on_tool_call):  # type: ignore[no-untyped-def]
        await on_token("Sure, I've proposed that.")
        record = ToolCallRecord(
            tool_name="propose_note",
            tool_input=json.dumps({"content": "Remember this."}),
            tool_output=self._proposal_tool_output,
        )
        await on_tool_call(record)
        return CustodianReply(content="Sure, I've proposed that.", tool_calls=[record])


@pytest.mark.asyncio
async def test_message_id_is_backfilled_onto_the_logged_item(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    async with session(seeded_user) as conn:
        from kernel.db.custodian import CustodianRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Remember this."},
        )
    fake = FakeCustodianWithProposal(json.dumps({"proposal_id": str(item.id), "status": "proposed"}))
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    async with client.stream(
        "POST", f"/custodian/sessions/{custodian_session.id}/messages", json={"content": "log it"}
    ) as response:
        await _drain_sse(response)

    async with session(seeded_user) as conn:
        backfilled = await CustodianLoggedItemRepository(conn).get(item.id)

    assert backfilled is not None
    assert backfilled.message_id is not None

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_accept_and_reject_endpoints(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        from kernel.db.custodian import CustodianRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        note_item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Accept me."},
        )
        reject_item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Reject me."},
        )

    await _login(client)
    listed = await client.get(f"/custodian/sessions/{custodian_session.id}/logged-items")
    accepted = await client.post(f"/custodian/logged-items/{note_item.id}/accept")
    rejected = await client.post(f"/custodian/logged-items/{reject_item.id}/reject")
    accept_again = await client.post(f"/custodian/logged-items/{note_item.id}/accept")

    assert len(listed.json()) == 2
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert accept_again.status_code == 409

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM notes"))
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
```

Add `from kernel.ai.custodian import CustodianReply, ToolCallRecord` to this test file's imports if `CustodianReply` isn't already imported (Plan 1's version of this file already imports `CustodianReply, ToolCallRecord` — reuse it).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/backend/test_custodian_api.py -k "backfilled or accept_and_reject" -v`
Expected: FAIL — `AttributeError: module 'backend.app.api.custodian' has no attribute 'CustodianLoggedItemRepository'` or 404s from missing routes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/backend/test_custodian_api.py -v`
Expected: all pass (6 total: the 4 from Plan 1 plus these 2).

- [ ] **Step 5: Run the full backend suite**

Run: `pytest tests/kernel/ tests/backend/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/custodian.py tests/backend/test_custodian_api.py
git commit -m "feat: add Custodian Logging list/accept/reject API and message_id backfill"
```

---

### Task 5: Frontend types and API client

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `CustodianLoggedItem`)
- Modify: `frontend/src/lib/api.ts` (add `listLoggedItems`, `acceptLoggedItem`, `rejectLoggedItem`)

**Interfaces:**
- Produces: `CustodianLoggedItem` type; `listLoggedItems(sessionId)`, `acceptLoggedItem(itemId)`, `rejectLoggedItem(itemId)` functions.
- Consumes: `req`, `readError`, `JSON_HEADERS` already in `frontend/src/lib/api.ts`.

- [ ] **Step 1: Add the type**

In `frontend/src/lib/types.ts`, add (near `CustodianMessage`):

```typescript
export interface CustodianLoggedItem {
  id: string
  sessionId: string
  itemType: string
  targetId: string | null
  content: Record<string, unknown>
  status: "proposed" | "accepted" | "rejected" | "superseded"
  createdAt: string
  resolvedAt: string | null
}
```

- [ ] **Step 2: Add the API client functions**

In `frontend/src/lib/api.ts`, add:

```typescript
function toCustodianLoggedItem(d: Record<string, unknown>): CustodianLoggedItem {
  return {
    id: String(d.id),
    sessionId: String(d.session_id),
    itemType: String(d.item_type),
    targetId: (d.target_id as string | null) ?? null,
    content: (d.content as Record<string, unknown>) ?? {},
    status: d.status as CustodianLoggedItem["status"],
    createdAt: String(d.created_at),
    resolvedAt: (d.resolved_at as string | null) ?? null,
  }
}

export async function listLoggedItems(sessionId: string): Promise<CustodianLoggedItem[]> {
  const r = await req(`/custodian/sessions/${sessionId}/logged-items`)
  if (!r.ok) throw await readError(r, "listLoggedItems failed")
  return (await r.json()).map(toCustodianLoggedItem)
}

export async function acceptLoggedItem(itemId: string): Promise<CustodianLoggedItem> {
  const r = await req(`/custodian/logged-items/${itemId}/accept`, { method: "POST" })
  if (!r.ok) throw await readError(r, "acceptLoggedItem failed")
  return toCustodianLoggedItem(await r.json())
}

export async function rejectLoggedItem(itemId: string): Promise<CustodianLoggedItem> {
  const r = await req(`/custodian/logged-items/${itemId}/reject`, { method: "POST" })
  if (!r.ok) throw await readError(r, "rejectLoggedItem failed")
  return toCustodianLoggedItem(await r.json())
}
```

Add `CustodianLoggedItem` to the type-only import at the top of the file.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: add Custodian Logging types and API client functions"
```

---

### Task 6: Proposal cards in the chat panel

**Files:**
- Create: `frontend/src/components/custodian/ProposalCard.tsx`
- Modify: `frontend/src/components/custodian/CustodianPanel.tsx` (render proposal cards inline, poll for new proposals after each assistant turn)
- Modify: `frontend/src/components/custodian/custodian.test.tsx`

**Interfaces:**
- Produces: `ProposalCard` component (`{ item: CustodianLoggedItem, onResolved: (item: CustodianLoggedItem) => void }`).
- Consumes: `acceptLoggedItem`, `rejectLoggedItem`, `listLoggedItems` (Task 5).

- [ ] **Step 1: Write a human-readable summary helper and the card**

Create `frontend/src/components/custodian/ProposalCard.tsx`:

```tsx
"use client"

import { useState } from "react"
import { acceptLoggedItem, rejectLoggedItem } from "@/lib/api"
import type { CustodianLoggedItem } from "@/lib/types"

function summarize(item: CustodianLoggedItem): string {
  const c = item.content
  switch (item.itemType) {
    case "observation":
      return `Log as observation: "${c.content}"`
    case "note":
      return `Save as note: "${c.content}"`
    case "claim":
      return `Log as claim (${c.claim_type}, ${c.assertion_type}): "${c.claim_text}"`
    case "task":
      return `Log as task: "${c.claim_text}"`
    case "concept_candidate":
      return `Link to concept "${c.candidate_name}" (${c.concept_type})`
    case "reality_assertion":
      return "Mark this claim as reality"
    case "perception_assertion":
      return "Mark this claim as perception"
    case "contradiction":
      return "Flag these two claims as contradicting each other"
    case "importance_signal":
      return `Pin this ${c.target_type} as important`
    default:
      return item.itemType
  }
}

export function ProposalCard({
  item,
  onResolved,
}: {
  item: CustodianLoggedItem
  onResolved: (item: CustodianLoggedItem) => void
}) {
  const [busy, setBusy] = useState(false)

  async function accept() {
    setBusy(true)
    onResolved(await acceptLoggedItem(item.id))
  }

  async function reject() {
    setBusy(true)
    onResolved(await rejectLoggedItem(item.id))
  }

  if (item.status !== "proposed") {
    return (
      <div className="text-xs text-muted italic px-3 py-2 border border-hairline rounded-meridian">
        {item.status === "accepted" ? `Logged: ${summarize(item)}` : "Rejected"}
      </div>
    )
  }

  return (
    <div className="border border-hairline rounded-meridian px-3 py-2 space-y-2">
      <div className="text-sm text-ink">{summarize(item)}</div>
      <div className="flex gap-2">
        <button
          onClick={accept}
          disabled={busy}
          className="px-2 py-1 rounded-meridian bg-accent text-canvas text-xs font-ui disabled:opacity-50"
        >
          Accept
        </button>
        <button
          onClick={reject}
          disabled={busy}
          className="px-2 py-1 rounded-meridian border border-hairline text-muted text-xs font-ui disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Render proposals inline in the panel**

In `frontend/src/components/custodian/CustodianPanel.tsx`, add the import:

```tsx
import { listLoggedItems } from "@/lib/api"
import { ProposalCard } from "@/components/custodian/ProposalCard"
import type { CustodianLoggedItem } from "@/lib/types"
```

Add state and load proposals whenever the active session changes or a turn finishes:

```tsx
  const [proposals, setProposals] = useState<CustodianLoggedItem[]>([])

  async function refreshProposals(sessionId: string) {
    setProposals(await listLoggedItems(sessionId))
  }
```

In the `useEffect` that already loads messages when `activeId` changes, also load proposals:

```tsx
  useEffect(() => {
    if (!activeId) {
      setMessages([])
      setProposals([])
      return
    }
    getCustodianMessages(activeId).then((msgs) => setMessages(msgs.map(toDisplay)))
    refreshProposals(activeId)
  }, [activeId])
```

In `send()`'s `onDone` handler, refresh proposals once generation finishes (a `propose_*` tool call may have just created one):

```tsx
      onDone() {
        setSending(false)
        if (activeId) refreshProposals(activeId)
      },
```

(`activeId` is already in scope inside `send()` from the surrounding closure — no new parameter needed.)

Render the proposal list below the message thread, above the input:

```tsx
      {proposals.filter((p) => p.status === "proposed").length > 0 && (
        <div className="px-4 py-2 space-y-2 border-t border-hairline">
          {proposals
            .filter((p) => p.status === "proposed")
            .map((p) => (
              <ProposalCard
                key={p.id}
                item={p}
                onResolved={(resolved) =>
                  setProposals((prev) => prev.map((x) => (x.id === resolved.id ? resolved : x)))
                }
              />
            ))}
        </div>
      )}
```

- [ ] **Step 3: Write the failing test**

In `frontend/src/components/custodian/custodian.test.tsx`, add to the `vi.mock("@/lib/api", ...)` block:

```typescript
  listLoggedItems: vi.fn().mockResolvedValue([]),
  acceptLoggedItem: vi.fn(),
  rejectLoggedItem: vi.fn(),
```

and add the corresponding named imports/mocks (`listLoggedItems`, `acceptLoggedItem`) alongside the existing `createCustodianSession`/`listCustodianSessions`/`streamCustodianMessage` ones, then add:

```tsx
it("shows a proposal card after a turn that proposes something, and accepting removes it", async () => {
  mockCreate.mockResolvedValueOnce({
    id: "s1",
    title: null,
    startedAt: "2024-05-12T14:32:01Z",
    endedAt: null,
    model: "gpt-4o-mini",
    provider: "openai",
  })
  const proposal = {
    id: "p1",
    sessionId: "s1",
    itemType: "note",
    targetId: null,
    content: { content: "Remember this." },
    status: "proposed" as const,
    createdAt: "2024-05-12T14:32:01Z",
    resolvedAt: null,
  }
  vi.mocked(listLoggedItems).mockResolvedValueOnce([]).mockResolvedValueOnce([proposal])
  mockStream.mockImplementationOnce(async (_id, _content, handlers) => {
    handlers.onDone()
  })
  vi.mocked(acceptLoggedItem).mockResolvedValueOnce({ ...proposal, status: "accepted" })

  renderOrb()
  await userEvent.click(screen.getByLabelText("Open the Custodian"))
  await userEvent.type(screen.getByPlaceholderText("Ask the Custodian..."), "log it")
  await userEvent.keyboard("{Enter}")

  await waitFor(() => {
    expect(screen.getByText(/Save as note/)).toBeInTheDocument()
  })

  await userEvent.click(screen.getByText("Accept"))

  await waitFor(() => {
    expect(screen.getByText(/Logged: Save as note/)).toBeInTheDocument()
  })
})
```

Add `listLoggedItems, acceptLoggedItem` to the file's existing `import { createCustodianSession, listCustodianSessions, streamCustodianMessage } from "@/lib/api"` line.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/custodian/custodian.test.tsx`
Expected: 3 passed (the 2 from Plan 1 plus this one).

- [ ] **Step 5: Run the full frontend suite and type-check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass, no type errors.

- [ ] **Step 6: Manual smoke check**

Run: `cd frontend && npm run dev`, open the Orb, send a message that would plausibly trigger a proposal (e.g. "log this as a note: buy milk") with `OPENAI_API_KEY` set, confirm a proposal card appears with Accept/Reject, and that accepting flips it to "Logged: ...".

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/custodian
git commit -m "feat: render Custodian proposals as inline accept/reject cards"
```

---

### Task 7: Docs

**Files:**
- Modify: `README.md` (add a "Phase 3 Custodian Logging" section)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the README section**

After the "Phase 3 Custodian Core" section (added by Plan 1), add:

```markdown
## Phase 3 Custodian Logging

During chat, the Custodian can propose new archive memory — nine kinds,
from freestanding creates (`observation`, `note`, `claim`, `task`,
`concept_candidate`) to actions on an existing claim/concept/observation
(`reality_assertion`, `perception_assertion`, `contradiction`,
`importance_signal`). Every proposal lands as a `proposed`
`custodian_logged_items` row and renders as a card in the chat panel with
Accept/Reject buttons — nothing is canonical until accepted.
`GET /api/custodian/sessions/{id}/logged-items`,
`POST /api/custodian/logged-items/{id}/accept`, and
`POST /api/custodian/logged-items/{id}/reject` drive this. Custodian-created
claims attach to a lazily-created `custodian`-type `Source` (never uploaded,
excluded from the normal ingestion type list) so they satisfy the same
`NOT NULL` source FK every other claim has. See
[docs/superpowers/specs/2026-07-09-custodian-logging-design.md](docs/superpowers/specs/2026-07-09-custodian-logging-design.md).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Custodian Logging's proposed-item workflow"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest && (cd frontend && npx vitest run && npx tsc --noEmit)`
- [ ] Run `alembic check` to confirm no unapplied migrations.
- [ ] Run `ruff check kernel/ backend/ worker/` and `mypy kernel/ backend/ worker/`.
- [ ] Manually smoke-test at least one proposal of each of the 9 item types via the Orb chat panel.
