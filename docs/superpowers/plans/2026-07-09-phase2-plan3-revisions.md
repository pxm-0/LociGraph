# Phase 2 Plan 3: Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give concepts a mutable `description` with full history: an LLM-synthesized revision when a contradiction is classified `evolution`, or a manually-authored revision the user writes directly at any time.

**Architecture:** A new `revisions` table plus `ConceptRepository`'s first-ever mutation method. The automatic path mirrors `detect_contradictions`'s worker shape exactly (settings dataclass, structured-output LLM call, self-healing, post-commit auto-enqueue). The manual path is a plain synchronous endpoint, no AI, no worker — matching how `approve_candidate` is synchronous by design. Both paths write to the same table and the same mutation, so "override an LLM synthesis" is just "write another revision."

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries), asyncpg, Postgres 16, OpenAI structured outputs, dramatiq + Redis, Next.js 14 (App Router)/React/TypeScript, pytest + vitest.

## Global Constraints

- The next migration revision is `0010` (heads: `0001`→...→`0009`).
- No DB `CHECK` constraints. `revisions.source` (`'llm_synthesis' | 'manual'`) is never user-supplied — both call sites hardcode the literal — so it needs no validation set, just the two consistent literal strings.
- Worker reliability tolerances mirror every other AI worker in this codebase exactly: `@dramatiq.actor(queue_name="extraction", max_retries=3, on_retry_exhausted="heal_create_revision")`, no custom `time_limit` (one LLM call). Self-healing reuses `worker/tasks/healing.py` unchanged (`MAX_HEAL_GENERATIONS=50`, `HEAL_DELAY_MS=30_000`) — do not duplicate.
- **No `*_AUTORUN` flag** gates the classify→revision auto-enqueue: classification is already a single, deliberate human action, unlike the bulk auto-triggers (`CLAIM_EXTRACTION_AUTORUN`/`EMBEDDING_AUTORUN`/`CONTRADICTION_AUTORUN`) that process many items automatically.
- The auto-enqueue job must be created and sent **only after** the transaction that produced the state it references has committed — the exact bug found and fixed in Phase 2 Plan 2's Task 4. Do not repeat it here.
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod.
- `strip_nul_bytes` (from `kernel/db/base_repository.py`) wraps every text field that can originate from LLM output or free-form user input before it hits an INSERT/UPDATE — matches the existing convention in `kernel/db/claims.py`, `kernel/db/concept_candidates.py`, and `kernel/db/contradictions.py`.
- Design reference: `docs/superpowers/specs/2026-07-09-revisions-design.md`.

---

### Task 1: Schema, model, and repository

**Files:**
- Create: `migrations/versions/0010_revisions.py`
- Modify: `kernel/models.py` (add `Revision`)
- Create: `kernel/db/revisions.py`
- Modify: `kernel/db/concepts.py` (add `update_description`)
- Create: `tests/kernel/test_revisions_repository.py`
- Modify: `tests/kernel/test_tenant_isolation.py` (add revision isolation test)

**Interfaces:**
- Produces: `Revision` dataclass (`id, user_id, concept_id, contradiction_id, source, previous_description, new_description, rationale, created_at`); `RevisionRepository(conn)` with `create(*, user_id, concept_id, contradiction_id, source, previous_description, new_description, rationale) -> Revision`, `get(revision_id) -> Revision | None`, `list(*, concept_id, limit=50, offset=0) -> list[Revision]`, `count(*, concept_id) -> int`; `ConceptRepository.update_description(concept_id, new_description) -> Concept | None`.
- Consumes: `kernel/db/base_repository.py`'s `BaseRepository`/`strip_nul_bytes`; `kernel/models.py`'s `Concept`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0010_revisions.py`:

```python
"""revisions — history of concept description changes

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-09
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

DATA_TABLES = ["revisions"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            contradiction_id UUID REFERENCES contradictions(id),
            source TEXT NOT NULL,
            previous_description TEXT,
            new_description TEXT NOT NULL,
            rationale TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX revisions_concept_idx ON revisions (user_id, concept_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON revisions TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS revisions CASCADE")
```

- [ ] **Step 2: Run the migration and verify it applies cleanly**

Run:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
.venv/bin/alembic upgrade head
```
Expected: no errors; `.venv/bin/alembic current` reports `0010`.

- [ ] **Step 3: Add `Revision` to `kernel/models.py`**

Add after the existing `Contradiction` dataclass (after its `from_row`, before `Job`):

```python
@dataclass(frozen=True, slots=True)
class Revision:
    id: UUID
    user_id: UUID
    concept_id: UUID
    contradiction_id: UUID | None
    source: str
    previous_description: str | None
    new_description: str
    rationale: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Revision:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_id=row["concept_id"],
            contradiction_id=row.get("contradiction_id"),
            source=row["source"],
            previous_description=row.get("previous_description"),
            new_description=row["new_description"],
            rationale=row.get("rationale"),
            created_at=row["created_at"],
        )
```

- [ ] **Step 4: Write the failing repository tests**

Create `tests/kernel/test_revisions_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_create_and_get_round_trip_manual_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await SourceRepository(conn).create(user_id, "json", "revisions-repo-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id,
            concept_type="idea",
            concept_name="Test Concept",
            description="Original description.",
        )
        repo = RevisionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=concept.description,
            new_description="Updated by hand.",
            rationale="I know better.",
        )
        fetched = await repo.get(created.id)

    assert created.source == "manual"
    assert created.contradiction_id is None
    assert created.previous_description == "Original description."
    assert created.new_description == "Updated by hand."
    assert fetched == created


@pytest.mark.asyncio
async def test_create_with_contradiction_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept B", description=None
        )
        repo = RevisionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            contradiction_id="00000000-0000-0000-0000-000000000000",
            source="llm_synthesis",
            previous_description=None,
            new_description="Synthesized text.",
            rationale="Claims evolved understanding.",
        )

    assert created.source == "llm_synthesis"
    assert str(created.contradiction_id) == "00000000-0000-0000-0000-000000000000"
    assert created.previous_description is None


@pytest.mark.asyncio
async def test_list_and_count_scoped_to_concept_newest_first(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept_a = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept A", description=None
        )
        concept_b = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept C", description=None
        )
        repo = RevisionRepository(conn)
        first = await repo.create(
            user_id=user_id,
            concept_id=concept_a.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="First revision.",
            rationale=None,
        )
        second = await repo.create(
            user_id=user_id,
            concept_id=concept_a.id,
            contradiction_id=None,
            source="manual",
            previous_description="First revision.",
            new_description="Second revision.",
            rationale=None,
        )
        await repo.create(
            user_id=user_id,
            concept_id=concept_b.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Unrelated concept's revision.",
            rationale=None,
        )

        revisions = await repo.list(concept_id=concept_a.id)
        count = await repo.count(concept_id=concept_a.id)

    assert [r.id for r in revisions] == [second.id, first.id]
    assert count == 2


@pytest.mark.asyncio
async def test_update_description_changes_concept_and_returns_it(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept D", description="Old."
        )
        repo = ConceptRepository(conn)

        updated = await repo.update_description(concept.id, "New.")
        fetched = await repo.get(concept.id)

    assert updated is not None
    assert updated.description == "New."
    assert fetched.description == "New."
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/kernel/test_revisions_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.db.revisions'`

- [ ] **Step 6: Implement `kernel/db/revisions.py`**

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Revision

_COLUMNS = (
    "id, user_id, concept_id, contradiction_id, source, "
    "previous_description, new_description, rationale, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class RevisionRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        concept_id: str | UUID,
        contradiction_id: str | UUID | None,
        source: str,
        previous_description: str | None,
        new_description: str,
        rationale: str | None,
    ) -> Revision:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO revisions
                        (user_id, concept_id, contradiction_id, source,
                         previous_description, new_description, rationale)
                    VALUES
                        (:user_id, :concept_id, :contradiction_id, :source,
                         :previous_description, :new_description, :rationale)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "concept_id": str(concept_id),
                    "contradiction_id": str(contradiction_id) if contradiction_id else None,
                    "source": source,
                    "previous_description": previous_description,
                    "new_description": strip_nul_bytes(new_description),
                    "rationale": strip_nul_bytes(rationale),
                },
            )
        ).mappings().one()
        return Revision.from_row(_as_mapping(row))

    async def get(self, revision_id: str | UUID) -> Revision | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM revisions WHERE id = :id"),
                {"id": str(revision_id)},
            )
        ).mappings().first()
        return Revision.from_row(_as_mapping(row)) if row else None

    async def list(
        self, *, concept_id: str | UUID, limit: int = 50, offset: int = 0
    ) -> list[Revision]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM revisions WHERE concept_id = :concept_id "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"concept_id": str(concept_id), "limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Revision.from_row(_as_mapping(r)) for r in rows]

    async def count(self, *, concept_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text("SELECT count(*) FROM revisions WHERE concept_id = :concept_id"),
                {"concept_id": str(concept_id)},
            )
        ).scalar_one()
        return result
```

- [ ] **Step 7: Add `update_description` to `ConceptRepository`**

In `kernel/db/concepts.py`, change the import line — from:
```python
from kernel.db.base_repository import BaseRepository
```
to:
```python
from kernel.db.base_repository import BaseRepository, strip_nul_bytes
```

Add this method after `create` (before `get`):

```python
    async def update_description(
        self, concept_id: str | UUID, new_description: str
    ) -> Concept | None:
        row = (
            await self.conn.execute(
                text(
                    f"UPDATE concepts SET description = :description WHERE id = :id "
                    f"RETURNING {_COLUMNS}"
                ),
                {"id": str(concept_id), "description": strip_nul_bytes(new_description)},
            )
        ).mappings().first()
        return Concept.from_row(_as_mapping(row)) if row else None
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_revisions_repository.py -v`
Expected: 4 passed

- [ ] **Step 9: Add tenant isolation coverage**

Add to `tests/kernel/test_tenant_isolation.py`:

```python
@pytest.mark.asyncio
async def test_revisions_isolated_between_tenants(make_user):
    from kernel.db.concepts import ConceptRepository
    from kernel.db.revisions import RevisionRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_a, concept_type="idea", concept_name="Secret Concept", description=None
        )
        revision = await RevisionRepository(conn).create(
            user_id=user_a,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Secret revision.",
            rationale=None,
        )

    async with session(user_b) as conn:
        assert await RevisionRepository(conn).list(concept_id=concept.id) == []
        assert await RevisionRepository(conn).get(revision.id) is None
```

Run: `.venv/bin/pytest tests/kernel/test_tenant_isolation.py -v`
Expected: all pass.

- [ ] **Step 10: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add migrations/versions/0010_revisions.py kernel/models.py kernel/db/revisions.py \
  kernel/db/concepts.py tests/kernel/test_revisions_repository.py \
  tests/kernel/test_tenant_isolation.py
git commit -m "feat: add revisions table, model, and repository with concept description mutation"
```

---

### Task 2: LLM revision synthesis

**Files:**
- Create: `kernel/ai/revision_synthesis.py`
- Create: `tests/kernel/test_revision_synthesis.py`

**Interfaces:**
- Produces: `RevisionSynthesisSettings` (`active_ai_provider, openai_api_key, openai_revision_model`, `from_env()`); `RevisionSynthesis` dataclass (`new_description: str, rationale: str`); `OpenAIRevisionSynthesizer` with `async synthesize(previous_description: str | None, claim_a_text: str, claim_a_assertion_type: str, claim_b_text: str, claim_b_assertion_type: str) -> RevisionSynthesis`; `get_revision_synthesizer(settings=None) -> OpenAIRevisionSynthesizer`.
- Consumes: nothing new — self-contained, mirrors `kernel/ai/contradiction_detection.py`'s shape.

- [ ] **Step 1: Write the failing tests**

Create `tests/kernel/test_revision_synthesis.py`:

```python
from __future__ import annotations

import json

import pytest

from kernel.ai.revision_synthesis import RevisionSynthesisSettings, _parse_revision_payload


def test_parses_valid_synthesis_response():
    payload = json.dumps(
        {
            "new_description": "The project moved from a monolith to microservices.",
            "rationale": "The second claim describes a completed migration.",
        }
    )
    result = _parse_revision_payload(payload)
    assert result.new_description == "The project moved from a monolith to microservices."
    assert result.rationale == "The second claim describes a completed migration."


def test_raises_when_new_description_empty():
    with pytest.raises(ValueError, match="new_description"):
        _parse_revision_payload(json.dumps({"new_description": "  ", "rationale": "x"}))


def test_raises_when_rationale_empty():
    with pytest.raises(ValueError, match="rationale"):
        _parse_revision_payload(json.dumps({"new_description": "x", "rationale": "  "}))


def test_raises_when_response_is_not_a_json_object():
    with pytest.raises(ValueError, match="JSON object"):
        _parse_revision_payload(json.dumps([1, 2, 3]))


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_REVISION_MODEL", raising=False)

    settings = RevisionSynthesisSettings.from_env()

    assert settings.openai_revision_model == "gpt-4o-mini"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/kernel/test_revision_synthesis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.ai.revision_synthesis'`

- [ ] **Step 3: Implement `kernel/ai/revision_synthesis.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RevisionSynthesisSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_revision_model: str

    @classmethod
    def from_env(cls) -> RevisionSynthesisSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_revision_model=os.environ.get("OPENAI_REVISION_MODEL", "gpt-4o-mini"),
        )


@dataclass(frozen=True, slots=True)
class RevisionSynthesis:
    new_description: str
    rationale: str


def _parse_revision_payload(payload: str) -> RevisionSynthesis:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("revision synthesis response must be a JSON object")
    new_description = str(data.get("new_description", "")).strip()
    if not new_description:
        raise ValueError("new_description cannot be empty")
    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        raise ValueError("rationale cannot be empty")
    return RevisionSynthesis(new_description=new_description, rationale=rationale)


class OpenAIRevisionSynthesizer:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def synthesize(
        self,
        previous_description: str | None,
        claim_a_text: str,
        claim_a_assertion_type: str,
        claim_b_text: str,
        claim_b_assertion_type: str,
    ) -> RevisionSynthesis:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "A user has classified two claims as an evolution in "
                        "understanding of a concept, not a conflict — the second "
                        "claim supersedes or refines the first, it doesn't just "
                        "disagree with it. Given the concept's current description "
                        "(if any) and both claims, write an updated description "
                        "that incorporates the new understanding, and briefly "
                        "explain what changed."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "previous_description": previous_description,
                            "claim_a": {
                                "text": claim_a_text,
                                "assertion_type": claim_a_assertion_type,
                            },
                            "claim_b": {
                                "text": claim_b_text,
                                "assertion_type": claim_b_assertion_type,
                            },
                        }
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "revision_synthesis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["new_description", "rationale"],
                        "properties": {
                            "new_description": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                    },
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return _parse_revision_payload(output_text)


def get_revision_synthesizer(
    settings: RevisionSynthesisSettings | None = None,
) -> OpenAIRevisionSynthesizer:
    settings = settings or RevisionSynthesisSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIRevisionSynthesizer(settings.openai_api_key, settings.openai_revision_model)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_revision_synthesis.py -v`
Expected: 5 passed

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add kernel/ai/revision_synthesis.py tests/kernel/test_revision_synthesis.py
git commit -m "feat: add LLM revision synthesis"
```

---

### Task 3: Worker task — `create_revision`

**Files:**
- Create: `worker/tasks/create_revision.py`
- Modify: `worker/main.py`
- Create: `tests/worker/test_create_revision.py`

**Interfaces:**
- Produces: `create_revision(contradiction_id: str, user_id: str, job_id: str)` dramatiq actor (queue `"extraction"`, `max_retries=3`, `on_retry_exhausted="heal_create_revision"`); `_create_revision(...)`; `heal_create_revision`/`_heal_create_revision`.
- Consumes: `kernel.ai.revision_synthesis.RevisionSynthesisSettings`/`get_revision_synthesizer` (Task 2); `kernel.db.revisions.RevisionRepository` (Task 1); `kernel.db.concepts.ConceptRepository.update_description` (Task 1); `kernel.db.contradictions.ContradictionRepository` (existing); `worker.tasks.healing.HEAL_DELAY_MS`/`next_heal_generation` (existing).

- [ ] **Step 1: Write the failing worker tests**

Create `tests/worker/test_create_revision.py`:

```python
from __future__ import annotations

import pytest

from kernel.ai.revision_synthesis import RevisionSynthesis
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.create_revision import (
    _create_revision,
    _heal_create_revision,
    create_revision,
)
from worker.tasks.healing import MAX_HEAL_GENERATIONS


class FakeSynthesizer:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def synthesize(
        self, previous_description, claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type
    ):  # type: ignore[no-untyped-def]
        self.calls.append(
            (previous_description, claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type)
        )
        return RevisionSynthesis(new_description="Synthesized text.", rationale="Fake rationale.")


async def _seed_contradiction(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "revision-worker")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description="Old."
        )
        claim_repo = ClaimRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claims = []
        for text_ in ["It rained.", "It was sunny, later than expected."]:
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": text_}], source.id, user_id
            )
            claim = await claim_repo.create(
                user_id=user_id,
                source_id=source.id,
                observation_id=obs_id,
                claim_text=text_,
                claim_type="fact",
                assertion_type="reality",
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            assert claim is not None
            candidate = await candidate_repo.create(
                user_id=user_id,
                source_id=source.id,
                claim_id=claim.id,
                candidate_name="Test Concept",
                concept_type="idea",
                rationale=None,
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            await edge_repo.create(
                user_id=user_id,
                claim_id=claim.id,
                concept_id=concept.id,
                concept_candidate_id=candidate.id,
                confidence=0.9,
            )
            claims.append(claim)
        contradiction = await ContradictionRepository(conn).create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claims[0].id,
            claim_b_id=claims[1].id,
            similarity=0.8,
            rationale="Detected rationale.",
        )
        assert contradiction is not None
        await ContradictionRepository(conn).classify(contradiction.id, "evolution")
        job = await JobRepository(conn).create(
            user_id, "create_revision", payload={"contradiction_id": str(contradiction.id)}
        )
    return concept, contradiction, job


@pytest.mark.asyncio
async def test_create_revision_synthesizes_and_updates_concept(make_user, monkeypatch):
    user_id = await make_user()
    concept, contradiction, job = await _seed_contradiction(user_id)
    fake = FakeSynthesizer()
    monkeypatch.setattr(
        "worker.tasks.create_revision.get_revision_synthesizer", lambda settings: fake
    )

    await _create_revision(str(contradiction.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        updated_concept = await ConceptRepository(conn).get(concept.id)
        revisions = await RevisionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert updated_concept.description == "Synthesized text."
    assert len(revisions) == 1
    assert revisions[0].source == "llm_synthesis"
    assert revisions[0].contradiction_id == contradiction.id
    assert revisions[0].previous_description == "Old."
    assert revisions[0].new_description == "Synthesized text."
    assert revisions[0].rationale == "Fake rationale."
    assert done.status == "completed"
    assert len(fake.calls) == 1


def test_create_revision_wired_to_heal_on_retry_exhausted():
    assert create_revision.options.get("on_retry_exhausted") == "heal_create_revision"


@pytest.mark.asyncio
async def test_heal_create_revision_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    _concept, contradiction, job = await _seed_contradiction(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.create_revision.create_revision.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(contradiction.id), str(user_id), str(job.id)),
        "options": {},
    }
    await _heal_create_revision(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    new_contradiction_id, new_user_id, new_job_id = sent["args"]
    assert new_contradiction_id == str(contradiction.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_create_revision_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    _concept, contradiction, job = await _seed_contradiction(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.create_revision.create_revision.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(contradiction.id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_create_revision(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/worker/test_create_revision.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.tasks.create_revision'`

- [ ] **Step 3: Implement `worker/tasks/create_revision.py`**

```python
from __future__ import annotations

import logging
from typing import Any

import dramatiq

from kernel.ai.revision_synthesis import RevisionSynthesisSettings, get_revision_synthesizer
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

logger = logging.getLogger(__name__)

get_broker()


async def _create_revision(contradiction_id: str, user_id: str, job_id: str) -> None:
    settings = RevisionSynthesisSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        contradiction = await ContradictionRepository(conn).get(contradiction_id)
        if contradiction is None:
            raise ValueError(f"contradiction {contradiction_id} not found")
        concept = await ConceptRepository(conn).get(contradiction.concept_id)
        if concept is None:
            raise ValueError(f"concept {contradiction.concept_id} not found")
        claim_a = await ClaimRepository(conn).get(contradiction.claim_a_id)
        claim_b = await ClaimRepository(conn).get(contradiction.claim_b_id)
        if claim_a is None or claim_b is None:
            raise ValueError(f"claims for contradiction {contradiction_id} not found")

    try:
        synthesizer = get_revision_synthesizer(settings)
        synthesis = await synthesizer.synthesize(
            concept.description,
            claim_a.claim_text,
            claim_a.assertion_type,
            claim_b.claim_text,
            claim_b.assertion_type,
        )
        async with session(user_id) as conn:
            await ConceptRepository(conn).update_description(
                concept.id, synthesis.new_description
            )
            await RevisionRepository(conn).create(
                user_id=user_id,
                concept_id=concept.id,
                contradiction_id=contradiction.id,
                source="llm_synthesis",
                previous_description=concept.description,
                new_description=synthesis.new_description,
                rationale=synthesis.rationale,
            )
            await JobRepository(conn).mark_completed(job_id, result={"revised": True})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_create_revision",
)
def create_revision(contradiction_id: str, user_id: str, job_id: str) -> None:
    run_actor(_create_revision(contradiction_id, user_id, job_id))


async def _heal_create_revision(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    contradiction_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "create_revision", payload={"contradiction_id": contradiction_id}
        )
    create_revision.send_with_options(
        args=(contradiction_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_create_revision(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_create_revision(original_message, stats))
```

- [ ] **Step 4: Register the actor in `worker/main.py`**

Change:
```python
from worker.tasks import (  # noqa: E402,F401
    detect_contradictions,
    embed_claims,
    extract_claims,
    ingest_source,
)
```
to:
```python
from worker.tasks import (  # noqa: E402,F401
    create_revision,
    detect_contradictions,
    embed_claims,
    extract_claims,
    ingest_source,
)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/worker/test_create_revision.py -v`
Expected: 4 passed

- [ ] **Step 6: Lint and type-check**

Run: `.venv/bin/ruff check kernel worker tests && .venv/bin/mypy kernel worker`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add worker/tasks/create_revision.py worker/main.py tests/worker/test_create_revision.py
git commit -m "feat: add create_revision worker task with self-healing"
```

---

### Task 4: Auto-enqueue wiring

**Files:**
- Modify: `backend/app/api/contradictions.py`
- Modify: `tests/backend/test_contradictions_api.py`

**Interfaces:**
- Consumes: `worker.tasks.create_revision.create_revision` (Task 3).
- Produces: nothing new for later tasks — this task only wires one existing call site.

- [ ] **Step 1: Write the failing tests**

Add to `tests/backend/test_contradictions_api.py` (this file already has a `_seed_contradiction` helper and `_login`; reuse them):

```python
@pytest.mark.asyncio
async def test_classify_evolution_auto_enqueues_revision_creation(client, seeded_user, monkeypatch):  # type: ignore[no-untyped-def]
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.contradictions.create_revision.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "classify-evolution-autorun")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "evolution"}
    )

    assert r.status_code == 200
    assert len(sent) == 1
    sent_contradiction_id, sent_user_id, _sent_job_id = sent[0]
    assert sent_contradiction_id == str(contradiction.id)
    assert sent_user_id == str(seeded_user)

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM revisions"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_non_evolution_does_not_enqueue_revision_creation(client, seeded_user, monkeypatch):  # type: ignore[no-untyped-def]
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.contradictions.create_revision.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "classify-non-evolution")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "true_conflict"}
    )

    assert r.status_code == 200
    assert sent == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/backend/test_contradictions_api.py -k revision_creation -v`
Expected: FAIL with `AttributeError: <module 'backend.app.api.contradictions'> does not have the attribute 'create_revision'`

- [ ] **Step 3: Wire the classify endpoint**

In `backend/app/api/contradictions.py`, change the imports — from:
```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.api.concepts import serialize_claim
from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.contradictions import CLASSIFICATIONS, ContradictionRepository
from kernel.db.session import session
from kernel.models import Contradiction

router = APIRouter()
```
to:
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.api.concepts import serialize_claim
from backend.app.auth.dependencies import get_current_user
from kernel.db.claims import ClaimRepository
from kernel.db.contradictions import CLASSIFICATIONS, ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.models import Contradiction
from worker.tasks.create_revision import create_revision

logger = logging.getLogger(__name__)

router = APIRouter()
```

Change `classify_contradiction` — from:
```python
@router.post("/contradictions/{contradiction_id}/classify")
async def classify_contradiction(
    contradiction_id: str,
    body: ClassifyBody,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.classification not in CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"classification must be one of {sorted(CLASSIFICATIONS)}",
        )
    async with session(user_id) as conn:
        contradiction = await ContradictionRepository(conn).classify(
            contradiction_id, body.classification
        )
        if contradiction is None:
            raise HTTPException(status_code=404, detail="not found")
        claims = ClaimRepository(conn)
        serialized = await _serialize_contradiction(contradiction, claims)
    assert serialized is not None
    return serialized
```
to:
```python
@router.post("/contradictions/{contradiction_id}/classify")
async def classify_contradiction(
    contradiction_id: str,
    body: ClassifyBody,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.classification not in CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"classification must be one of {sorted(CLASSIFICATIONS)}",
        )
    async with session(user_id) as conn:
        contradiction = await ContradictionRepository(conn).classify(
            contradiction_id, body.classification
        )
        if contradiction is None:
            raise HTTPException(status_code=404, detail="not found")
        claims = ClaimRepository(conn)
        serialized = await _serialize_contradiction(contradiction, claims)
    assert serialized is not None
    # Auto-enqueue revision synthesis AFTER the classify transaction commits
    # (deliberately outside the session block above): sending the dramatiq
    # message before commit risks create_revision picking it up and reading
    # a contradiction row that isn't visible yet under READ COMMITTED
    # isolation — the exact bug fixed in Phase 2 Plan 2's auto-enqueue wiring.
    if body.classification == "evolution":
        try:
            async with session(user_id) as conn:
                revision_job = await JobRepository(conn).create(
                    user_id,
                    "create_revision",
                    payload={"contradiction_id": contradiction_id},
                )
            create_revision.send(contradiction_id, user_id, str(revision_job.id))
        except Exception as exc:
            logger.warning(
                "failed to auto-enqueue create_revision for contradiction %s: %s",
                contradiction_id,
                exc,
            )
    return serialized
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/backend/test_contradictions_api.py -v`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check backend tests && .venv/bin/mypy backend`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/contradictions.py tests/backend/test_contradictions_api.py
git commit -m "feat: auto-enqueue revision synthesis when a contradiction is classified evolution"
```

---

### Task 5: API — manual revisions and history

**Files:**
- Modify: `backend/app/api/concepts.py`
- Create: `tests/backend/test_concept_revisions_api.py`

**Interfaces:**
- Produces: `GET /concepts/{concept_id}/revisions?limit=&offset=`; `POST /concepts/{concept_id}/revisions` (body `{"new_description": str, "rationale": str | None}`); `serialize_revision(revision) -> dict[str, Any]`.
- Consumes: `kernel.db.revisions.RevisionRepository` (Task 1); `kernel.db.concepts.ConceptRepository.update_description` (Task 1).

- [ ] **Step 1: Write the failing API tests**

Create `tests/backend/test_concept_revisions_api.py`:

```python
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.concepts import ConceptRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_create_manual_revision_updates_concept_and_records_history(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=seeded_user,
            concept_type="idea",
            concept_name="Manual Concept",
            description="Original.",
        )

    await _login(client)
    r = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "Rewritten by hand.", "rationale": "I know better."},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["contradiction_id"] is None
    assert body["previous_description"] == "Original."
    assert body["new_description"] == "Rewritten by hand."
    assert body["rationale"] == "I know better."

    concept_r = await client.get(f"/concepts/{concept.id}")
    assert concept_r.json()["description"] == "Rewritten by hand."

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM revisions"))
        await conn.execute(text("DELETE FROM concepts"))


@pytest.mark.asyncio
async def test_create_manual_revision_404s_for_unknown_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/concepts/00000000-0000-0000-0000-000000000000/revisions",
        json={"new_description": "x", "rationale": None},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_revisions_returns_newest_first(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=seeded_user, concept_type="idea", concept_name="History Concept", description=None
        )

    await _login(client)
    first = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "First.", "rationale": None},
    )
    second = await client.post(
        f"/concepts/{concept.id}/revisions",
        json={"new_description": "Second.", "rationale": None},
    )
    listing = await client.get(f"/concepts/{concept.id}/revisions")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listing.status_code == 200
    body = listing.json()
    assert [r["new_description"] for r in body] == ["Second.", "First."]

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM revisions"))
        await conn.execute(text("DELETE FROM concepts"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/backend/test_concept_revisions_api.py -v`
Expected: FAIL with `404 Not Found` for all requests (no `/concepts/{id}/revisions` route registered yet).

- [ ] **Step 3: Implement the endpoints**

In `backend/app/api/concepts.py`, change the imports — from:
```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.session import session
from kernel.models import Claim, ClaimConceptEdge, Concept

router = APIRouter()
```
to:
```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from kernel.models import Claim, ClaimConceptEdge, Concept, Revision

router = APIRouter()


class CreateRevisionBody(BaseModel):
    new_description: str
    rationale: str | None = None


def serialize_revision(revision: Revision) -> dict[str, Any]:
    return {
        "id": str(revision.id),
        "concept_id": str(revision.concept_id),
        "contradiction_id": str(revision.contradiction_id)
        if revision.contradiction_id
        else None,
        "source": revision.source,
        "previous_description": revision.previous_description,
        "new_description": revision.new_description,
        "rationale": revision.rationale,
        "created_at": revision.created_at.isoformat(),
    }
```

Add these two endpoints at the end of the file, after `list_concept_claims`:

```python
@router.get("/concepts/{concept_id}/revisions")
async def list_concept_revisions(
    concept_id: str,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).get(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="not found")
        revisions = await RevisionRepository(conn).list(
            concept_id=concept_id, limit=limit, offset=offset
        )
        return [serialize_revision(r) for r in revisions]


@router.post("/concepts/{concept_id}/revisions")
async def create_concept_revision(
    concept_id: str,
    body: CreateRevisionBody,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        concepts = ConceptRepository(conn)
        concept = await concepts.get(concept_id)
        if concept is None:
            raise HTTPException(status_code=404, detail="not found")
        await concepts.update_description(concept_id, body.new_description)
        revision = await RevisionRepository(conn).create(
            user_id=user_id,
            concept_id=concept_id,
            contradiction_id=None,
            source="manual",
            previous_description=concept.description,
            new_description=body.new_description,
            rationale=body.rationale,
        )
    return serialize_revision(revision)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/backend/test_concept_revisions_api.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full backend/kernel/worker suite**

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
```
Expected: all pass, zero failures.

- [ ] **Step 6: Lint and type-check**

Run: `.venv/bin/ruff check kernel backend worker tests && .venv/bin/mypy kernel backend worker`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/concepts.py tests/backend/test_concept_revisions_api.py
git commit -m "feat: add manual revision creation and revision history API"
```

---

### Task 6: Frontend — concept detail page

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `Revision`)
- Modify: `frontend/src/lib/api.ts` (add `getConceptRevisions`, `createConceptRevision`)
- Modify: `frontend/src/app/(app)/concepts/page.tsx` (link rows to the detail page)
- Create: `frontend/src/app/(app)/concepts/[id]/page.tsx`
- Create: `frontend/src/app/(app)/concepts/[id]/concept-detail.test.tsx`

**Interfaces:**
- Produces: `Revision` TS type; `getConceptRevisions(conceptId) -> Promise<Revision[]>`; `createConceptRevision(conceptId, newDescription, rationale?) -> Promise<Revision>`; the `/concepts/[id]` page.
- Consumes: `backend/app/api/concepts.py`'s new endpoints (Task 5); the existing `getConcept`/`getConceptClaims` (already defined, `getConceptClaims` currently unused by any page).

- [ ] **Step 1: Write the failing frontend test**

Create `frontend/src/app/(app)/concepts/[id]/concept-detail.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Claim, Concept, Revision } from "@/lib/types"
import ConceptDetailPage from "./page"

vi.mock("@/lib/api", () => ({
  getConcept: vi.fn(),
  getConceptClaims: vi.fn().mockResolvedValue([]),
  getConceptRevisions: vi.fn().mockResolvedValue([]),
  createConceptRevision: vi.fn(),
}))

import {
  createConceptRevision,
  getConcept,
  getConceptClaims,
  getConceptRevisions,
} from "@/lib/api"
const mockGetConcept = vi.mocked(getConcept)
const mockGetConceptClaims = vi.mocked(getConceptClaims)
const mockGetConceptRevisions = vi.mocked(getConceptRevisions)
const mockCreateConceptRevision = vi.mocked(createConceptRevision)

function makeConcept(overrides: Partial<Concept> = {}): Concept {
  return {
    id: "concept-1",
    conceptName: "Careful Plans",
    conceptType: "idea",
    description: "Original description.",
    status: "active",
    createdAt: "2024-05-12T14:32:01Z",
    claimCount: 2,
    ...overrides,
  }
}

function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    id: "claim-1",
    sourceId: "src-1",
    observationId: "obs-1",
    claimText: "The user prefers small careful plans.",
    claimType: "preference",
    assertionType: "perception",
    confidence: 0.9,
    extractionMethod: "llm",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-05-12T14:32:01Z",
    ...overrides,
  }
}

function makeRevision(overrides: Partial<Revision> = {}): Revision {
  return {
    id: "rev-1",
    conceptId: "concept-1",
    contradictionId: null,
    source: "manual",
    previousDescription: "Older text.",
    newDescription: "Original description.",
    rationale: "Because I said so.",
    createdAt: "2024-05-10T00:00:00Z",
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ThemeProvider>
      <ConceptDetailPage params={{ id: "concept-1" }} />
    </ThemeProvider>,
  )
}

describe("ConceptDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetConceptClaims.mockResolvedValue([])
    mockGetConceptRevisions.mockResolvedValue([])
  })

  it("shows the concept's name, description, claims, and revision history", async () => {
    mockGetConcept.mockResolvedValueOnce(makeConcept())
    mockGetConceptClaims.mockResolvedValueOnce([makeClaim()])
    mockGetConceptRevisions.mockResolvedValueOnce([makeRevision()])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("Careful Plans")).toBeInTheDocument()
      expect(screen.getByText("Original description.")).toBeInTheDocument()
      expect(screen.getByText("The user prefers small careful plans.")).toBeInTheDocument()
      expect(screen.getByText("Because I said so.")).toBeInTheDocument()
    })
  })

  it("submits a manual revision and shows it immediately", async () => {
    mockGetConcept.mockResolvedValueOnce(makeConcept())
    mockCreateConceptRevision.mockResolvedValueOnce(
      makeRevision({
        id: "rev-2",
        previousDescription: "Original description.",
        newDescription: "Rewritten by hand.",
        rationale: null,
      })
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("Careful Plans")).toBeInTheDocument()
    })

    await userEvent.type(
      screen.getByLabelText("New description"),
      "Rewritten by hand."
    )
    await userEvent.click(screen.getByRole("button", { name: /save revision/i }))

    await waitFor(() => {
      expect(mockCreateConceptRevision).toHaveBeenCalledWith(
        "concept-1",
        "Rewritten by hand.",
        undefined
      )
      expect(screen.getByText("Rewritten by hand.")).toBeInTheDocument()
    })
  })

  it("shows a not-found message when the concept doesn't exist", async () => {
    mockGetConcept.mockResolvedValueOnce(null)
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/concept not found/i)).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run "src/app/(app)/concepts/[id]/concept-detail.test.tsx"`
Expected: FAIL — module `./page` doesn't exist.

- [ ] **Step 3: Add the `Revision` type**

In `frontend/src/lib/types.ts`, add after the `Concept` interface:

```ts
export interface Revision {
  id: string
  conceptId: string
  contradictionId: string | null
  source: string
  previousDescription: string | null
  newDescription: string
  rationale: string | null
  createdAt: string
}
```

- [ ] **Step 4: Add the API client functions**

In `frontend/src/lib/api.ts`, add `Revision` to the type import list — change:
```ts
import type {
  Claim,
  Concept,
  ConceptCandidate,
  Contradiction,
  DashboardSummary,
  Job,
  Observation,
  SearchResult,
  Source,
  SourceType,
} from "./types"
```
to:
```ts
import type {
  Claim,
  Concept,
  ConceptCandidate,
  Contradiction,
  DashboardSummary,
  Job,
  Observation,
  Revision,
  SearchResult,
  Source,
  SourceType,
} from "./types"
```

Add right after the existing `getConceptClaims` function:
```ts
export async function getConceptClaims(conceptId: string): Promise<Claim[]> {
  const r = await req(`/concepts/${conceptId}/claims`)
  if (!r.ok) throw await readError(r, "getConceptClaims failed")
  return (await r.json()).map(toClaim)
}
```
insert this new block immediately after it:
```ts
function toRevision(d: Record<string, unknown>): Revision {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    contradictionId: (d.contradiction_id as string | null) ?? null,
    source: String(d.source),
    previousDescription: (d.previous_description as string | null) ?? null,
    newDescription: String(d.new_description),
    rationale: (d.rationale as string | null) ?? null,
    createdAt: String(d.created_at),
  }
}

export async function getConceptRevisions(conceptId: string): Promise<Revision[]> {
  const r = await req(`/concepts/${conceptId}/revisions`)
  if (!r.ok) throw await readError(r, "getConceptRevisions failed")
  return (await r.json()).map(toRevision)
}

export async function createConceptRevision(
  conceptId: string,
  newDescription: string,
  rationale?: string
): Promise<Revision> {
  const r = await req(`/concepts/${conceptId}/revisions`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ new_description: newDescription, rationale: rationale ?? null }),
  })
  if (!r.ok) throw await readError(r, "createConceptRevision failed")
  return toRevision(await r.json())
}
```

- [ ] **Step 5: Implement the concept detail page**

Create `frontend/src/app/(app)/concepts/[id]/page.tsx`:

```tsx
"use client"

import { useEffect, useState } from "react"
import {
  createConceptRevision,
  getConcept,
  getConceptClaims,
  getConceptRevisions,
} from "@/lib/api"
import type { Claim, Concept, Revision } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

export default function ConceptDetailPage({ params }: { params: { id: string } }) {
  const conceptId = params.id
  const [concept, setConcept] = useState<Concept | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [revisions, setRevisions] = useState<Revision[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [newDescription, setNewDescription] = useState("")
  const [rationale, setRationale] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    getConcept(conceptId)
      .then((data) => {
        if (cancelled) return
        if (data === null) {
          setNotFound(true)
          return
        }
        setConcept(data)
        return Promise.all([getConceptClaims(conceptId), getConceptRevisions(conceptId)]).then(
          ([claimsData, revisionsData]) => {
            if (!cancelled) {
              setClaims(claimsData)
              setRevisions(revisionsData)
            }
          }
        )
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load concept")
        }
      })
    return () => {
      cancelled = true
    }
  }, [conceptId])

  async function handleSubmitRevision() {
    if (!newDescription.trim() || submitting) return
    setSubmitting(true)
    try {
      const revision = await createConceptRevision(
        conceptId,
        newDescription.trim(),
        rationale.trim() || undefined
      )
      setRevisions((prev) => [revision, ...(prev ?? [])])
      setConcept((prev) => (prev ? { ...prev, description: revision.newDescription } : prev))
      setNewDescription("")
      setRationale("")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create revision")
    } finally {
      setSubmitting(false)
    }
  }

  if (notFound) {
    return (
      <div className="space-y-6 p-8">
        <p className="text-sm text-muted">Concept not found.</p>
      </div>
    )
  }

  if (concept === null) {
    return (
      <div className="space-y-6 p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24" />
      </div>
    )
  }

  return (
    <div className="space-y-8 p-8">
      <div className="space-y-2">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-ink">{concept.conceptName}</h1>
          <Badge className="font-mono uppercase">{concept.conceptType}</Badge>
        </div>
        <p className="text-sm leading-6 text-ink">
          {concept.description ?? "No description yet."}
        </p>
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          {error}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Write a revision</h2>
        <textarea
          aria-label="New description"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setNewDescription(event.target.value)}
          placeholder="Write the updated understanding of this concept"
          rows={3}
          value={newDescription}
        />
        <input
          aria-label="Rationale (optional)"
          className="w-full rounded-hearth border border-hairline bg-canvas px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Rationale (optional)"
          value={rationale}
        />
        <button
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={submitting || !newDescription.trim()}
          onClick={handleSubmitRevision}
          type="button"
        >
          {submitting ? "Saving…" : "Save revision"}
        </button>
      </section>

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Claims</h2>
        <div className="divide-y divide-hairline border-y border-hairline">
          {(claims ?? []).map((claim) => (
            <article className="grid gap-3 py-4 md:grid-cols-[1fr_160px]" key={claim.id}>
              <p className="text-sm leading-6 text-ink">{claim.claimText}</p>
              <div className="flex flex-wrap gap-1">
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
                <Badge className="font-mono uppercase">{claim.assertionType}</Badge>
              </div>
            </article>
          ))}
          {claims !== null && claims.length === 0 ? (
            <p className="py-8 text-sm text-muted">No claims linked yet.</p>
          ) : null}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-heading text-lg text-ink">Revision history</h2>
        <div className="divide-y divide-hairline border-y border-hairline">
          {(revisions ?? []).map((revision) => (
            <article className="space-y-1 py-4" key={revision.id}>
              <div className="flex items-center gap-2">
                <Badge className="font-mono uppercase">{revision.source}</Badge>
                <span className="font-mono text-xs text-muted">{revision.createdAt}</span>
              </div>
              <p className="text-sm leading-6 text-muted line-through">
                {revision.previousDescription ?? "(no prior description)"}
              </p>
              <p className="text-sm leading-6 text-ink">{revision.newDescription}</p>
              {revision.rationale ? (
                <p className="text-sm text-muted">{revision.rationale}</p>
              ) : null}
            </article>
          ))}
          {revisions !== null && revisions.length === 0 ? (
            <p className="py-8 text-sm text-muted">No revisions yet.</p>
          ) : null}
        </div>
      </section>
    </div>
  )
}
```

- [ ] **Step 6: Link the concepts list into the detail page**

In `frontend/src/app/(app)/concepts/page.tsx`, add the import — change:
```tsx
"use client"

import { useEffect, useState } from "react"
import { getConceptsCount, listConcepts } from "@/lib/api"
import type { Concept } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"
```
to:
```tsx
"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { getConceptsCount, listConcepts } from "@/lib/api"
import type { Concept } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"
```

Change the name cell — from:
```tsx
                <td className="px-5 py-3 font-heading text-ink">{concept.conceptName}</td>
```
to:
```tsx
                <td className="px-5 py-3 font-heading text-ink">
                  <Link className="hover:underline" href={`/concepts/${concept.id}`}>
                    {concept.conceptName}
                  </Link>
                </td>
```

- [ ] **Step 7: Run the tests, type-check, and lint**

Run:
```bash
cd frontend
npx vitest run "src/app/(app)/concepts/[id]/concept-detail.test.tsx"
npx vitest run "src/app/(app)/concepts/concepts.test.tsx"
npx tsc --noEmit
npx eslint src
```
Expected: all pass, no type errors, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/lib/types.ts" "frontend/src/lib/api.ts" \
  "frontend/src/app/(app)/concepts/page.tsx" \
  "frontend/src/app/(app)/concepts/[id]/page.tsx" \
  "frontend/src/app/(app)/concepts/[id]/concept-detail.test.tsx"
git commit -m "feat: add concept detail page with revision history and manual revision authoring"
```

---

### Task 7: Docs

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: no code — documentation and env-var wiring only.

- [ ] **Step 1: Add the new env var**

In `.env.example`, change:
```
OPENAI_CONTRADICTION_MODEL=gpt-4o-mini
CONTRADICTION_CANDIDATE_LIMIT=5
CONTRADICTION_SIMILARITY_FLOOR=0.75
CONTRADICTION_AUTORUN=false
```
to:
```
OPENAI_CONTRADICTION_MODEL=gpt-4o-mini
CONTRADICTION_CANDIDATE_LIMIT=5
CONTRADICTION_SIMILARITY_FLOOR=0.75
CONTRADICTION_AUTORUN=false
OPENAI_REVISION_MODEL=gpt-4o-mini
```

In `docker-compose.yml`, both the `backend:` and `worker:` service blocks — change:
```yaml
      OPENAI_CONTRADICTION_MODEL: ${OPENAI_CONTRADICTION_MODEL:-gpt-4o-mini}
      CONTRADICTION_CANDIDATE_LIMIT: ${CONTRADICTION_CANDIDATE_LIMIT:-5}
      CONTRADICTION_SIMILARITY_FLOOR: ${CONTRADICTION_SIMILARITY_FLOOR:-0.75}
      CONTRADICTION_AUTORUN: ${CONTRADICTION_AUTORUN:-false}
```
to:
```yaml
      OPENAI_CONTRADICTION_MODEL: ${OPENAI_CONTRADICTION_MODEL:-gpt-4o-mini}
      CONTRADICTION_CANDIDATE_LIMIT: ${CONTRADICTION_CANDIDATE_LIMIT:-5}
      CONTRADICTION_SIMILARITY_FLOOR: ${CONTRADICTION_SIMILARITY_FLOOR:-0.75}
      CONTRADICTION_AUTORUN: ${CONTRADICTION_AUTORUN:-false}
      OPENAI_REVISION_MODEL: ${OPENAI_REVISION_MODEL:-gpt-4o-mini}
```
(both the `backend:` and `worker:` service blocks need this addition).

- [ ] **Step 2: Add a README section**

In `README.md`, insert after the "Phase 2 Contradictions" section (before "## Project Layout"):

```markdown
---

## Phase 2 Revisions

Concepts have their first mutable field: `description`. Every change is
recorded in a `revisions` table — append-only, two sources. Classifying a
contradiction `evolution` auto-enqueues an LLM call that synthesizes an
updated description from both claims and the concept's current
understanding. Independently, `POST /api/concepts/{id}/revisions` lets you
write a concept's description directly at any time — no contradiction, no
LLM required. Both paths converge on the same table and the same mutation,
so overriding a synthesized description you don't like is just writing
another revision on top; revisions are immutable once created.

`GET /api/concepts/{id}/revisions` lists a concept's full history, newest
first. The `/concepts/{id}` page (the app's first concept detail view) shows
the concept's claims and revision history side by side, with a form to
author a manual revision. This completes Phase 2 — Contradictions and
Revisions are two of the three original scope items with Reality/Perception
Separation; see
[docs/superpowers/specs/2026-07-09-revisions-design.md](docs/superpowers/specs/2026-07-09-revisions-design.md).

---
```

- [ ] **Step 3: Run the full gate one final time**

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

- [ ] **Step 4: QA**

Start the stack (`docker compose up -d --build`), log in, and verify (skip the LLM-dependent parts if `OPENAI_API_KEY` isn't configured in this environment — verify those via direct psql/curl instead, same substitution used in Phase 2 Plan 2's docs task):
- `POST /api/concepts/{id}/revisions` updates a concept's description and appears in `GET /api/concepts/{id}/revisions`.
- The `/concepts/{id}` page renders the concept, its claims, its revision history, and the manual-revision form; submitting the form updates the visible description immediately.
- If a real API key is available: classify a contradiction `evolution` and confirm a `llm_synthesis`-sourced revision appears shortly after.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example docker-compose.yml
git commit -m "docs: document revisions — LLM-synthesized and manual concept history"
```
