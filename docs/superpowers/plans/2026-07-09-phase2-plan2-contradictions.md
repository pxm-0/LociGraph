# Phase 2 Plan 2: Contradictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect pairs of claims linked to the same concept that conflict (semantic-similarity-assisted, LLM-confirmed), store them as unresolved-by-default contradictions per ADR-005, and let a user manually classify each one.

**Architecture:** A new `contradictions` table plus a new async worker task (`detect_contradictions`) that mirrors `extract_claims`/`embed_claims` exactly — same reliability tolerances, same self-healing, same auto-enqueue-after-the-previous-stage pattern. Detection narrows candidates via the existing per-claim embeddings before spending an LLM call, exactly like the rest of this codebase's AI pipeline stages.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries), asyncpg, Postgres 16 + pgvector, dramatiq + Redis, OpenAI structured outputs, Next.js/React/TypeScript, pytest + vitest.

## Global Constraints

- The next migration revision is `0009` (heads: `0001`→`0002`→`0003`→`0004`→`0005`→`0006`→`0007`→`0008`).
- No DB `CHECK` constraints — `classification` is validated in Python via `CLASSIFICATIONS` in `kernel/db/contradictions.py`, checked at the API layer (the same "validate at the data-entry point, not in the DB" pattern already used for `claim_type`/`assertion_type`).
- `ContradictionRepository.create` stores `claim_a_id`/`claim_b_id` in canonical order (the two claim ids sorted as strings) so a unique index on `(user_id, claim_a_id, claim_b_id)` catches a reversed-order duplicate too — ordering is enforced in Python, not the database.
- Worker reliability tolerances **mirror `extract_claims`/`embed_claims` exactly**: `@dramatiq.actor(queue_name="extraction", max_retries=3, on_retry_exhausted="heal_detect_contradictions")`, no custom `time_limit` (job is bounded to at most `CONTRADICTION_CANDIDATE_LIMIT` LLM calls, comfortably inside dramatiq's default 10-minute limit). Self-healing reuses the existing `worker/tasks/healing.py` (`MAX_HEAL_GENERATIONS=50`, `HEAL_DELAY_MS=30_000`) — do not duplicate this logic.
- `CONTRADICTION_AUTORUN` (env var, default `false`) gates both auto-enqueue call sites, mirroring `CLAIM_EXTRACTION_AUTORUN`/`EMBEDDING_AUTORUN` — every pipeline stage that auto-triggers the next AI-cost-incurring stage uses the same opt-in convention.
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod, matching every existing model in `kernel/models.py`.
- All repository methods take an already-open `AsyncConnection` via `BaseRepository.__init__`; RLS scoping happens implicitly through `kernel/db/session.py`'s `session(user_id)` context manager.
- Design reference: `docs/superpowers/specs/2026-07-09-contradictions-design.md`.

---

### Task 1: Schema, model, and repository

**Files:**
- Create: `migrations/versions/0009_contradictions.py`
- Modify: `kernel/models.py` (add `Contradiction`)
- Create: `kernel/db/contradictions.py`
- Create: `tests/kernel/test_contradictions_repository.py`
- Modify: `tests/kernel/test_tenant_isolation.py` (add contradiction isolation test)

**Interfaces:**
- Produces: `Contradiction` dataclass (`id, user_id, concept_id, claim_a_id, claim_b_id, similarity, classification, rationale, created_at, classified_at`); `CLASSIFICATIONS = {"true_conflict", "evolution", "contextual_difference", "both"}`; `ContradictionRepository(conn)` with `create(*, user_id, concept_id, claim_a_id, claim_b_id, similarity, rationale) -> Contradiction | None`, `get(contradiction_id) -> Contradiction | None`, `list(*, concept_id=None, classification=None, limit=50, offset=0) -> list[Contradiction]`, `count(*, concept_id=None, classification=None) -> int`, `classify(contradiction_id, classification) -> Contradiction | None`.
- Consumes: `kernel/db/base_repository.py`'s `BaseRepository`/`strip_nul_bytes`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0009_contradictions.py`:

```python
"""contradictions between claims linked to the same concept

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-09
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

DATA_TABLES = ["contradictions"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contradictions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            claim_a_id UUID NOT NULL REFERENCES claims(id),
            claim_b_id UUID NOT NULL REFERENCES claims(id),
            similarity NUMERIC NOT NULL,
            classification TEXT NOT NULL DEFAULT 'unresolved',
            rationale TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            classified_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX contradictions_unique_pair ON contradictions "
        "(user_id, claim_a_id, claim_b_id)"
    )
    op.execute(
        "CREATE INDEX contradictions_concept_idx ON contradictions (user_id, concept_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON contradictions TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS contradictions CASCADE")
```

- [ ] **Step 2: Run the migration and verify it applies cleanly**

Run:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
.venv/bin/alembic upgrade head
```
Expected: no errors; `.venv/bin/alembic current` reports `0009`.

- [ ] **Step 3: Add `Contradiction` to `kernel/models.py`**

Add after the existing `ClaimConceptEdge` dataclass (after its `from_row`, before `Job`):

```python
@dataclass(frozen=True, slots=True)
class Contradiction:
    id: UUID
    user_id: UUID
    concept_id: UUID
    claim_a_id: UUID
    claim_b_id: UUID
    similarity: float
    classification: str
    rationale: str
    created_at: datetime
    classified_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Contradiction:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_id=row["concept_id"],
            claim_a_id=row["claim_a_id"],
            claim_b_id=row["claim_b_id"],
            similarity=float(row["similarity"]),
            classification=row["classification"],
            rationale=row["rationale"],
            created_at=row["created_at"],
            classified_at=row.get("classified_at"),
        )
```

- [ ] **Step 4: Write the failing repository tests**

Create `tests/kernel/test_contradictions_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _make_claim_linked_to_concept(conn, user_id, source_id, concept_id, content):  # type: ignore[no-untyped-def]
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": content}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=obs_id,
        claim_text=content,
        claim_type="fact",
        assertion_type="reality",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    assert claim is not None
    candidate = await ConceptCandidateRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        claim_id=claim.id,
        candidate_name="Test Concept",
        concept_type="idea",
        rationale=None,
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    await ClaimConceptEdgeRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        concept_id=concept_id,
        concept_candidate_id=candidate.id,
        confidence=0.9,
    )
    return claim


@pytest.mark.asyncio
async def test_create_and_get_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-1")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It rained."
        )
        claim_b = await _make_claim_linked_to_concept(
            conn, user_id, source.id, concept.id, "It was sunny."
        )
        repo = ContradictionRepository(conn)

        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.81,
            rationale="Both claims describe the weather at the same time but disagree.",
        )
        fetched = await repo.get(created.id)

    assert created is not None
    assert created.classification == "unresolved"
    assert created.classified_at is None
    assert fetched == created


@pytest.mark.asyncio
async def test_create_dedups_a_reversed_pair(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        repo = ContradictionRepository(conn)

        first = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )
        # Same pair, reversed order, as a second detection run might produce
        # (the "new" claim in one direction is the "candidate" in the other).
        second = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_b.id,
            claim_b_id=claim_a.id,
            similarity=0.8,
            rationale="r2",
        )
        all_rows = await repo.list(concept_id=concept.id)

    assert first is not None
    assert second is None
    assert len(all_rows) == 1
    assert {str(all_rows[0].claim_a_id), str(all_rows[0].claim_b_id)} == {
        str(claim_a.id),
        str(claim_b.id),
    }


@pytest.mark.asyncio
async def test_list_and_count_filter_by_classification(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-3")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        claim_c = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "C.")
        repo = ContradictionRepository(conn)
        first = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )
        await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_c.id,
            similarity=0.8,
            rationale="r2",
        )
        await repo.classify(first.id, "evolution")

        unresolved = await repo.list(concept_id=concept.id, classification="unresolved")
        unresolved_count = await repo.count(concept_id=concept.id, classification="unresolved")
        evolved = await repo.list(concept_id=concept.id, classification="evolution")

    assert len(unresolved) == 1
    assert unresolved_count == 1
    assert [c.id for c in evolved] == [first.id]


@pytest.mark.asyncio
async def test_classify_sets_classification_and_classified_at(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradictions-repo-4")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_a = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "A.")
        claim_b = await _make_claim_linked_to_concept(conn, user_id, source.id, concept.id, "B.")
        repo = ContradictionRepository(conn)
        created = await repo.create(
            user_id=user_id,
            concept_id=concept.id,
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            similarity=0.8,
            rationale="r1",
        )

        classified = await repo.classify(created.id, "true_conflict")

    assert classified is not None
    assert classified.classification == "true_conflict"
    assert classified.classified_at is not None
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/kernel/test_contradictions_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.db.contradictions'`

- [ ] **Step 6: Implement `kernel/db/contradictions.py`**

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Contradiction

_COLUMNS = (
    "id, user_id, concept_id, claim_a_id, claim_b_id, similarity, "
    "classification, rationale, created_at, classified_at"
)

CLASSIFICATIONS = {"true_conflict", "evolution", "contextual_difference", "both"}


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ContradictionRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        concept_id: str | UUID,
        claim_a_id: str | UUID,
        claim_b_id: str | UUID,
        similarity: float,
        rationale: str,
    ) -> Contradiction | None:
        a_id, b_id = sorted([str(claim_a_id), str(claim_b_id)])
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO contradictions
                        (user_id, concept_id, claim_a_id, claim_b_id, similarity, rationale)
                    VALUES
                        (:user_id, :concept_id, :claim_a_id, :claim_b_id, :similarity, :rationale)
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "concept_id": str(concept_id),
                    "claim_a_id": a_id,
                    "claim_b_id": b_id,
                    "similarity": similarity,
                    "rationale": strip_nul_bytes(rationale),
                },
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None

    async def get(self, contradiction_id: str | UUID) -> Contradiction | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM contradictions WHERE id = :id"),
                {"id": str(contradiction_id)},
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None

    async def list(
        self,
        *,
        concept_id: str | UUID | None = None,
        classification: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Contradiction]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if concept_id is not None:
            clauses.append("concept_id = :concept_id")
            params["concept_id"] = str(concept_id)
        if classification is not None:
            clauses.append("classification = :classification")
            params["classification"] = classification
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM contradictions {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [Contradiction.from_row(_as_mapping(r)) for r in rows]

    async def count(
        self,
        *,
        concept_id: str | UUID | None = None,
        classification: str | None = None,
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if concept_id is not None:
            clauses.append("concept_id = :concept_id")
            params["concept_id"] = str(concept_id)
        if classification is not None:
            clauses.append("classification = :classification")
            params["classification"] = classification
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        result: int = (
            await self.conn.execute(
                text(f"SELECT count(*) FROM contradictions {where}"), params
            )
        ).scalar_one()
        return result

    async def classify(
        self, contradiction_id: str | UUID, classification: str
    ) -> Contradiction | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE contradictions
                    SET classification = :classification, classified_at = now()
                    WHERE id = :id
                    RETURNING {_COLUMNS}
                    """
                ),
                {"id": str(contradiction_id), "classification": classification},
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_contradictions_repository.py -v`
Expected: 4 passed

- [ ] **Step 8: Add tenant isolation coverage**

Add to `tests/kernel/test_tenant_isolation.py` (uses the same helper pattern as the file's existing tests):

```python
@pytest.mark.asyncio
async def test_contradictions_isolated_between_tenants(make_user):
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.concepts import ConceptRepository
    from kernel.db.contradictions import ContradictionRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-contradictions")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_a, concept_type="idea", concept_name="Secret Concept", description=None
        )
        claims = []
        for text_ in ["Secret claim A.", "Secret claim B."]:
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": text_}], src.id, user_a
            )
            claim = await ClaimRepository(conn).create(
                user_id=user_a,
                source_id=src.id,
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
            candidate = await ConceptCandidateRepository(conn).create(
                user_id=user_a,
                source_id=src.id,
                claim_id=claim.id,
                candidate_name="Secret Concept",
                concept_type="idea",
                rationale=None,
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            await ClaimConceptEdgeRepository(conn).create(
                user_id=user_a,
                claim_id=claim.id,
                concept_id=concept.id,
                concept_candidate_id=candidate.id,
                confidence=0.9,
            )
            claims.append(claim)
        contradiction = await ContradictionRepository(conn).create(
            user_id=user_a,
            concept_id=concept.id,
            claim_a_id=claims[0].id,
            claim_b_id=claims[1].id,
            similarity=0.8,
            rationale="Secret rationale.",
        )
        assert contradiction is not None

    async with session(user_b) as conn:
        assert await ContradictionRepository(conn).list(concept_id=concept.id) == []
        assert await ContradictionRepository(conn).get(contradiction.id) is None
```

Run: `.venv/bin/pytest tests/kernel/test_tenant_isolation.py -v`
Expected: all pass.

- [ ] **Step 9: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add migrations/versions/0009_contradictions.py kernel/models.py kernel/db/contradictions.py \
  tests/kernel/test_contradictions_repository.py tests/kernel/test_tenant_isolation.py
git commit -m "feat: add contradictions table, model, and repository"
```

---

### Task 2: Detection building blocks — concept-scoped similarity search and LLM check

**Files:**
- Modify: `kernel/db/semantic_vectors.py` (add `search_similar_within_concept`)
- Modify: `tests/kernel/test_semantic_vectors_repository.py`
- Create: `kernel/ai/contradiction_detection.py`
- Create: `tests/kernel/test_contradiction_detection.py`

**Interfaces:**
- Produces: `SemanticVectorRepository.search_similar_within_concept(*, concept_id, exclude_claim_id, query_embedding, limit=5) -> list[SimilarClaim]`; `ContradictionSettings` (`active_ai_provider, openai_api_key, openai_contradiction_model, contradiction_candidate_limit, contradiction_similarity_floor, contradiction_autorun`, `from_env()` classmethod); `ContradictionCheck` dataclass (`is_contradiction: bool, rationale: str`); `OpenAIContradictionDetector` with `async check(claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type) -> ContradictionCheck`; `get_contradiction_detector(settings=None) -> OpenAIContradictionDetector`.
- Consumes: `kernel/models.py`'s `Claim`, `SimilarClaim` (from Task 1's neighbor); `kernel/db/base_repository.py`.

- [ ] **Step 1: Write the failing repository test**

Add to `tests/kernel/test_semantic_vectors_repository.py` (add these imports to the top of the file alongside the existing ones):

```python
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
```

Add this test:

```python
@pytest.mark.asyncio
async def test_search_similar_within_concept_excludes_other_concepts_and_self(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "sv-repo-5")
        concept_a = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept A", description=None
        )
        concept_b = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Concept B", description=None
        )
        target = await _make_claim(conn, user_id, source.id, "Target claim.")
        same_concept = await _make_claim(conn, user_id, source.id, "Same concept claim.")
        other_concept = await _make_claim(conn, user_id, source.id, "Other concept claim.")

        edge_repo = ClaimConceptEdgeRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        for claim, concept in [
            (target, concept_a),
            (same_concept, concept_a),
            (other_concept, concept_b),
        ]:
            candidate = await candidate_repo.create(
                user_id=user_id,
                source_id=source.id,
                claim_id=claim.id,
                candidate_name=concept.concept_name,
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

        vector_repo = SemanticVectorRepository(conn)
        await vector_repo.create(
            user_id=user_id, claim_id=target.id, embedding=[1.0, 0.0], model_name="test"
        )
        await vector_repo.create(
            user_id=user_id, claim_id=same_concept.id, embedding=[0.9, 0.1], model_name="test"
        )
        await vector_repo.create(
            user_id=user_id, claim_id=other_concept.id, embedding=[1.0, 0.0], model_name="test"
        )

        results = await vector_repo.search_similar_within_concept(
            concept_id=concept_a.id,
            exclude_claim_id=target.id,
            query_embedding=[1.0, 0.0],
            limit=5,
        )

    assert [r.claim.id for r in results] == [same_concept.id]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/test_semantic_vectors_repository.py::test_search_similar_within_concept_excludes_other_concepts_and_self -v`
Expected: FAIL with `AttributeError: 'SemanticVectorRepository' object has no attribute 'search_similar_within_concept'`

- [ ] **Step 3: Implement `search_similar_within_concept`**

Add to `kernel/db/semantic_vectors.py`, after `search_similar`:

```python
    async def search_similar_within_concept(
        self,
        *,
        concept_id: str | UUID,
        exclude_claim_id: str | UUID,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[SimilarClaim]:
        rows = (
            await self.conn.execute(
                text(
                    f"""
                    SELECT {_CLAIM_COLUMNS},
                           1 - (sv.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                    FROM semantic_vectors sv
                    JOIN claims c ON c.id = sv.claim_id
                    JOIN claim_concept_edges cce ON cce.claim_id = c.id
                    WHERE cce.concept_id = :concept_id AND c.id != :exclude_claim_id
                    ORDER BY sv.embedding <=> CAST(:query_embedding AS vector) ASC
                    LIMIT :limit
                    """
                ),
                {
                    "concept_id": str(concept_id),
                    "exclude_claim_id": str(exclude_claim_id),
                    "query_embedding": _embedding_literal(query_embedding),
                    "limit": limit,
                },
            )
        ).mappings().all()
        return [
            SimilarClaim(claim=Claim.from_row(_as_mapping(r)), similarity=float(r["similarity"]))
            for r in rows
        ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/kernel/test_semantic_vectors_repository.py -v`
Expected: all pass, including the new test.

- [ ] **Step 5: Write the failing contradiction-detection tests**

Create `tests/kernel/test_contradiction_detection.py`:

```python
from __future__ import annotations

import json

import pytest

from kernel.ai.contradiction_detection import ContradictionSettings, _parse_contradiction_payload


def test_parses_valid_contradiction_response():
    payload = json.dumps(
        {"is_contradiction": True, "rationale": "They disagree about the weather."}
    )
    result = _parse_contradiction_payload(payload)
    assert result.is_contradiction is True
    assert result.rationale == "They disagree about the weather."


def test_parses_non_contradiction_response():
    payload = json.dumps({"is_contradiction": False, "rationale": "Different topics."})
    result = _parse_contradiction_payload(payload)
    assert result.is_contradiction is False


def test_raises_when_is_contradiction_missing():
    with pytest.raises(ValueError, match="is_contradiction"):
        _parse_contradiction_payload(json.dumps({"rationale": "x"}))


def test_raises_when_rationale_empty():
    with pytest.raises(ValueError, match="rationale"):
        _parse_contradiction_payload(json.dumps({"is_contradiction": True, "rationale": "  "}))


def test_raises_when_response_is_not_a_json_object():
    with pytest.raises(ValueError, match="JSON object"):
        _parse_contradiction_payload(json.dumps([1, 2, 3]))


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CONTRADICTION_MODEL", raising=False)
    monkeypatch.delenv("CONTRADICTION_CANDIDATE_LIMIT", raising=False)
    monkeypatch.delenv("CONTRADICTION_SIMILARITY_FLOOR", raising=False)
    monkeypatch.delenv("CONTRADICTION_AUTORUN", raising=False)

    settings = ContradictionSettings.from_env()

    assert settings.openai_contradiction_model == "gpt-4o-mini"
    assert settings.contradiction_candidate_limit == 5
    assert settings.contradiction_similarity_floor == 0.75
    assert settings.contradiction_autorun is False
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/kernel/test_contradiction_detection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.ai.contradiction_detection'`

- [ ] **Step 7: Implement `kernel/ai/contradiction_detection.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContradictionSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_contradiction_model: str
    contradiction_candidate_limit: int
    contradiction_similarity_floor: float
    contradiction_autorun: bool

    @classmethod
    def from_env(cls) -> ContradictionSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_contradiction_model=os.environ.get(
                "OPENAI_CONTRADICTION_MODEL", "gpt-4o-mini"
            ),
            contradiction_candidate_limit=max(
                1, int(os.environ.get("CONTRADICTION_CANDIDATE_LIMIT", "5"))
            ),
            contradiction_similarity_floor=float(
                os.environ.get("CONTRADICTION_SIMILARITY_FLOOR", "0.75")
            ),
            contradiction_autorun=os.environ.get("CONTRADICTION_AUTORUN", "false").lower()
            == "true",
        )


@dataclass(frozen=True, slots=True)
class ContradictionCheck:
    is_contradiction: bool
    rationale: str


def _parse_contradiction_payload(payload: str) -> ContradictionCheck:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("contradiction detection response must be a JSON object")
    is_contradiction = data.get("is_contradiction")
    if not isinstance(is_contradiction, bool):
        raise ValueError("is_contradiction must be a boolean")
    rationale = str(data.get("rationale", "")).strip()
    if not rationale:
        raise ValueError("rationale cannot be empty")
    return ContradictionCheck(is_contradiction=is_contradiction, rationale=rationale)


class OpenAIContradictionDetector:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def check(
        self,
        claim_a_text: str,
        claim_a_assertion_type: str,
        claim_b_text: str,
        claim_b_assertion_type: str,
    ) -> ContradictionCheck:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Given two claims, decide whether they contradict each other — "
                        "state opposing facts, incompatible beliefs, or conflicting "
                        "accounts of the same thing. Two claims about different topics, "
                        "or a fact alongside an unrelated feeling, are not contradictions. "
                        "Explain your reasoning briefly."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
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
                    "name": "contradiction_check",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["is_contradiction", "rationale"],
                        "properties": {
                            "is_contradiction": {"type": "boolean"},
                            "rationale": {"type": "string"},
                        },
                    },
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ValueError("OpenAI response did not include output_text")
        return _parse_contradiction_payload(output_text)


def get_contradiction_detector(
    settings: ContradictionSettings | None = None,
) -> OpenAIContradictionDetector:
    settings = settings or ContradictionSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIContradictionDetector(
        settings.openai_api_key, settings.openai_contradiction_model
    )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_contradiction_detection.py tests/kernel/test_semantic_vectors_repository.py -v`
Expected: all pass.

- [ ] **Step 9: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add kernel/db/semantic_vectors.py tests/kernel/test_semantic_vectors_repository.py \
  kernel/ai/contradiction_detection.py tests/kernel/test_contradiction_detection.py
git commit -m "feat: add similarity search scoped to a concept and LLM contradiction detection"
```

---

### Task 3: Worker task — `detect_contradictions`

**Files:**
- Create: `worker/tasks/detect_contradictions.py`
- Modify: `worker/main.py`
- Create: `tests/worker/test_detect_contradictions.py`

**Interfaces:**
- Produces: `detect_contradictions(concept_id: str, claim_id: str, user_id: str, job_id: str)` dramatiq actor (queue `"extraction"`, `max_retries=3`, `on_retry_exhausted="heal_detect_contradictions"`); `_detect_contradictions(...)` (the plain async function, for direct testing); `heal_detect_contradictions` actor + `_heal_detect_contradictions`.
- Consumes: `kernel.ai.contradiction_detection.ContradictionSettings`/`get_contradiction_detector` (Task 2); `kernel.db.contradictions.ContradictionRepository` (Task 1); `kernel.db.semantic_vectors.SemanticVectorRepository.search_similar_within_concept`/`get_for_claim` (Task 2 / existing); `worker.tasks.healing.HEAL_DELAY_MS`/`next_heal_generation` (existing).

- [ ] **Step 1: Write the failing worker tests**

Create `tests/worker/test_detect_contradictions.py`:

```python
from __future__ import annotations

import pytest

from kernel.ai.contradiction_detection import ContradictionCheck
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.detect_contradictions import (
    _detect_contradictions,
    _heal_detect_contradictions,
    detect_contradictions,
)
from worker.tasks.healing import MAX_HEAL_GENERATIONS


class FakeDetector:
    def __init__(self, is_contradiction: bool = True) -> None:
        self.is_contradiction = is_contradiction
        self.calls: list[tuple[str, str, str, str]] = []

    async def check(self, claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type):  # type: ignore[no-untyped-def]
        self.calls.append(
            (claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type)
        )
        return ContradictionCheck(is_contradiction=self.is_contradiction, rationale="fake rationale")


def _pad_vector(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_concept_with_two_linked_claims(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradiction-worker")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_repo = ClaimRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claims = []
        for text_ in ["It rained.", "It was sunny."]:
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
        vector_repo = SemanticVectorRepository(conn)
        await vector_repo.create(
            user_id=user_id, claim_id=claims[0].id, embedding=_pad_vector([1.0, 0.0]), model_name="test"
        )
        await vector_repo.create(
            user_id=user_id, claim_id=claims[1].id, embedding=_pad_vector([0.9, 0.1]), model_name="test"
        )
        job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": str(concept.id), "claim_id": str(claims[0].id)},
        )
    return concept, claims, job


@pytest.mark.asyncio
async def test_detect_contradictions_creates_a_row_when_llm_flags_a_pair(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    fake = FakeDetector(is_contradiction=True)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert len(rows) == 1
    assert done.status == "completed"
    assert done.result == {"contradictions_found": 1}
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_detect_contradictions_creates_nothing_when_llm_says_no_contradiction(
    make_user, monkeypatch
):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    fake = FakeDetector(is_contradiction=False)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert rows == []
    assert done.result == {"contradictions_found": 0}


@pytest.mark.asyncio
async def test_detect_contradictions_skips_when_claim_has_no_embedding_yet(make_user, monkeypatch):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradiction-worker-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Unembedded claim."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Unembedded claim.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": str(concept.id), "claim_id": str(claim.id)},
        )
    fake = FakeDetector()
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claim.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
    assert done.status == "completed"
    assert done.result == {"contradictions_found": 0, "skipped": "no_embedding_yet"}
    assert fake.calls == []


@pytest.mark.asyncio
async def test_detect_contradictions_filters_out_candidates_below_similarity_floor(
    make_user, monkeypatch
):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    monkeypatch.setenv("CONTRADICTION_SIMILARITY_FLOOR", "0.999")
    fake = FakeDetector(is_contradiction=True)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
    assert rows == []
    assert fake.calls == []


def test_detect_contradictions_wired_to_heal_on_retry_exhausted():
    assert detect_contradictions.options.get("on_retry_exhausted") == "heal_detect_contradictions"


@pytest.mark.asyncio
async def test_heal_detect_contradictions_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.detect_contradictions.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(concept.id), str(claims[0].id), str(user_id), str(job.id)),
        "options": {},
    }
    await _heal_detect_contradictions(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    new_concept_id, new_claim_id, new_user_id, new_job_id = sent["args"]
    assert new_concept_id == str(concept.id)
    assert new_claim_id == str(claims[0].id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_detect_contradictions_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.detect_contradictions.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(concept.id), str(claims[0].id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_detect_contradictions(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/worker/test_detect_contradictions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.tasks.detect_contradictions'`

- [ ] **Step 3: Implement `worker/tasks/detect_contradictions.py`**

```python
from __future__ import annotations

import logging
from typing import Any

import dramatiq

from kernel.ai.contradiction_detection import ContradictionSettings, get_contradiction_detector
from kernel.db.claims import ClaimRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

logger = logging.getLogger(__name__)

get_broker()


async def _detect_contradictions(
    concept_id: str, claim_id: str, user_id: str, job_id: str
) -> None:
    settings = ContradictionSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        vector = await SemanticVectorRepository(conn).get_for_claim(claim_id)
        if vector is None:
            await JobRepository(conn).mark_completed(
                job_id, result={"contradictions_found": 0, "skipped": "no_embedding_yet"}
            )
            return
        candidates = await SemanticVectorRepository(conn).search_similar_within_concept(
            concept_id=concept_id,
            exclude_claim_id=claim_id,
            query_embedding=vector.embedding,
            limit=settings.contradiction_candidate_limit,
        )
        claim = await ClaimRepository(conn).get(claim_id)

    try:
        found = 0
        detector = get_contradiction_detector(settings)
        for candidate in candidates:
            if candidate.similarity < settings.contradiction_similarity_floor:
                continue
            check = await detector.check(
                claim.claim_text,
                claim.assertion_type,
                candidate.claim.claim_text,
                candidate.claim.assertion_type,
            )
            if not check.is_contradiction:
                continue
            async with session(user_id) as conn:
                created = await ContradictionRepository(conn).create(
                    user_id=user_id,
                    concept_id=concept_id,
                    claim_a_id=claim_id,
                    claim_b_id=str(candidate.claim.id),
                    similarity=candidate.similarity,
                    rationale=check.rationale,
                )
                if created is not None:
                    found += 1

        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id, result={"contradictions_found": found}
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_detect_contradictions",
)
def detect_contradictions(concept_id: str, claim_id: str, user_id: str, job_id: str) -> None:
    run_actor(_detect_contradictions(concept_id, claim_id, user_id, job_id))


async def _heal_detect_contradictions(
    original_message: dict[str, Any], stats: dict[str, Any]
) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    concept_id, claim_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": concept_id, "claim_id": claim_id},
        )
    detect_contradictions.send_with_options(
        args=(concept_id, claim_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_detect_contradictions(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_detect_contradictions(original_message, stats))
```

- [ ] **Step 4: Register the actor in `worker/main.py`**

Change:
```python
from worker.tasks import embed_claims, extract_claims, ingest_source  # noqa: E402,F401
```
to:
```python
from worker.tasks import (  # noqa: E402,F401
    detect_contradictions,
    embed_claims,
    extract_claims,
    ingest_source,
)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/worker/test_detect_contradictions.py -v`
Expected: 7 passed

- [ ] **Step 6: Lint and type-check**

Run: `.venv/bin/ruff check kernel worker tests && .venv/bin/mypy kernel worker`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add worker/tasks/detect_contradictions.py worker/main.py tests/worker/test_detect_contradictions.py
git commit -m "feat: add detect_contradictions worker task with self-healing"
```

---

### Task 4: Auto-enqueue wiring

**Files:**
- Modify: `worker/tasks/extract_claims.py`
- Modify: `backend/app/api/claims.py`
- Modify: `tests/worker/test_extract_claims.py`
- Modify: `tests/backend/test_claims_api.py`

**Interfaces:**
- Consumes: `worker.tasks.detect_contradictions.detect_contradictions` (Task 3); `kernel.ai.contradiction_detection.ContradictionSettings` (Task 2); `kernel.concepts_promotion.approve_candidate`'s `ApprovalResult.edge` (`concept_id`, `claim_id`, existing).
- Produces: nothing new for later tasks — this task only wires two existing call sites.

- [ ] **Step 1: Write the failing worker tests**

Add to `tests/worker/test_extract_claims.py` (these reuse the existing `_seed_verified_source` helper and `FakeExtractor` already defined in this file):

```python
@pytest.mark.asyncio
async def test_extract_claims_auto_enqueues_contradiction_detection_when_flag_set(
    make_user, monkeypatch
):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setenv("CONTRADICTION_AUTORUN", "true")
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    assert len(sent) == 1
    _sent_concept_id, _sent_claim_id, sent_user_id, _sent_job_id = sent[0]
    assert sent_user_id == str(user_id)


@pytest.mark.asyncio
async def test_extract_claims_does_not_enqueue_contradiction_detection_when_flag_unset(
    make_user, monkeypatch
):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.delenv("CONTRADICTION_AUTORUN", raising=False)
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "worker.tasks.extract_claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )

    await _extract_claims(str(source.id), str(user_id), str(job.id))

    assert sent == []


@pytest.mark.asyncio
async def test_extract_claims_stays_completed_when_contradiction_enqueue_fails(
    make_user, monkeypatch
):
    user_id = await make_user()
    source, job = await _seed_verified_source(user_id)
    monkeypatch.setenv("CONTRADICTION_AUTORUN", "true")
    monkeypatch.setattr(
        "worker.tasks.extract_claims.get_claim_extractor",
        lambda settings: FakeExtractor(),
    )
    monkeypatch.setattr(
        "worker.tasks.extract_claims.detect_contradictions.send",
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/worker/test_extract_claims.py -k contradiction -v`
Expected: FAIL with `AttributeError: <module 'worker.tasks.extract_claims'> does not have the attribute 'detect_contradictions'`

- [ ] **Step 3: Wire the auto-promotion loop**

In `worker/tasks/extract_claims.py`, add imports — change:
```python
from kernel.ai.claim_extraction import ClaimExtractionSettings, get_claim_extractor
from kernel.ai.embeddings import EmbeddingSettings
from kernel.concepts_promotion import approve_candidate
```
to:
```python
from kernel.ai.claim_extraction import ClaimExtractionSettings, get_claim_extractor
from kernel.ai.contradiction_detection import ContradictionSettings
from kernel.ai.embeddings import EmbeddingSettings
from kernel.concepts_promotion import approve_candidate
```
and:
```python
from worker.tasks.embed_claims import embed_claims
```
to:
```python
from worker.tasks.detect_contradictions import detect_contradictions
from worker.tasks.embed_claims import embed_claims
```

Compute the contradiction settings once per job — change:
```python
async def _extract_claims(
    source_id: str,
    user_id: str,
    job_id: str,
    force: bool = False,
    observation_ids: list[str] | None = None,
) -> None:
    settings = ClaimExtractionSettings.from_env()
```
to:
```python
async def _extract_claims(
    source_id: str,
    user_id: str,
    job_id: str,
    force: bool = False,
    observation_ids: list[str] | None = None,
) -> None:
    settings = ClaimExtractionSettings.from_env()
    contradiction_settings = ContradictionSettings.from_env()
```

Wire the auto-enqueue right after auto-promotion — change:
```python
                        candidate_count += 1
                        # Auto-promote: at this volume, requiring a human to
                        # click "approve" on every single candidate isn't
                        # viable, so a freshly extracted candidate goes
                        # straight to being a concept linked to its claim.
                        await approve_candidate(conn, created_candidate.id)
```
to:
```python
                        candidate_count += 1
                        # Auto-promote: at this volume, requiring a human to
                        # click "approve" on every single candidate isn't
                        # viable, so a freshly extracted candidate goes
                        # straight to being a concept linked to its claim.
                        approval = await approve_candidate(conn, created_candidate.id)
                        # Auto-enqueue contradiction detection for this newly
                        # linked claim, same failure-isolation shape as the
                        # embed_claims auto-enqueue below: a broker/config
                        # failure here must never corrupt this already-good
                        # candidate/edge state or the extraction job's result.
                        if contradiction_settings.contradiction_autorun:
                            try:
                                contradiction_job = await JobRepository(conn).create(
                                    user_id,
                                    "detect_contradictions",
                                    payload={
                                        "concept_id": str(approval.edge.concept_id),
                                        "claim_id": str(approval.edge.claim_id),
                                    },
                                )
                                detect_contradictions.send(
                                    str(approval.edge.concept_id),
                                    str(approval.edge.claim_id),
                                    user_id,
                                    str(contradiction_job.id),
                                )
                            except Exception as exc:
                                logger.warning(
                                    "failed to auto-enqueue detect_contradictions "
                                    "for claim %s: %s",
                                    approval.edge.claim_id,
                                    exc,
                                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/worker/test_extract_claims.py -v`
Expected: all pass (including the 3 new tests).

- [ ] **Step 5: Write the failing API tests**

Add to `tests/backend/test_claims_api.py`:

```python
@pytest.mark.asyncio
async def test_approve_candidate_auto_enqueues_contradiction_detection_when_flag_set(
    client, seeded_user, monkeypatch
):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CONTRADICTION_AUTORUN", "true")
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "approve-autorun-on")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha is useful."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Alpha is useful.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r.status_code == 200
    assert len(sent) == 1

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_approve_candidate_does_not_enqueue_contradiction_detection_when_flag_unset(
    client, seeded_user, monkeypatch
):  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CONTRADICTION_AUTORUN", raising=False)
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "approve-autorun-off")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Beta is useful."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Beta is useful.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Beta",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r.status_code == 200
    assert sent == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/backend/test_claims_api.py -k contradiction -v`
Expected: FAIL with `AttributeError: <module 'backend.app.api.claims'> does not have the attribute 'detect_contradictions'`

- [ ] **Step 7: Wire the manual approve endpoint**

In `backend/app/api/claims.py`, change the imports — from:
```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.concepts import serialize_claim, serialize_concept, serialize_edge
from backend.app.auth.dependencies import get_current_user
from kernel.concepts_promotion import CandidateNotPromotable, approve_candidate
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.session import session
from kernel.models import ConceptCandidate

router = APIRouter()
```
to:
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.concepts import serialize_claim, serialize_concept, serialize_edge
from backend.app.auth.dependencies import get_current_user
from kernel.ai.contradiction_detection import ContradictionSettings
from kernel.concepts_promotion import CandidateNotPromotable, approve_candidate
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.models import ConceptCandidate
from worker.tasks.detect_contradictions import detect_contradictions

logger = logging.getLogger(__name__)

router = APIRouter()
```

Change `approve_concept_candidate` — from:
```python
@router.post("/concept-candidates/{candidate_id}/approve")
async def approve_concept_candidate(
    candidate_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            result = await approve_candidate(conn, candidate_id)
        except CandidateNotPromotable as exc:
            status_code = 404 if exc.reason == "not_found" else 409
            raise HTTPException(status_code=status_code, detail=exc.message) from exc
        concept_dict = await serialize_concept(result.concept, ConceptRepository(conn))
    return {
        "concept": concept_dict,
        "edge": serialize_edge(result.edge),
    }
```
to:
```python
@router.post("/concept-candidates/{candidate_id}/approve")
async def approve_concept_candidate(
    candidate_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with session(user_id) as conn:
        try:
            result = await approve_candidate(conn, candidate_id)
        except CandidateNotPromotable as exc:
            status_code = 404 if exc.reason == "not_found" else 409
            raise HTTPException(status_code=status_code, detail=exc.message) from exc
        concept_dict = await serialize_concept(result.concept, ConceptRepository(conn))
        if ContradictionSettings.from_env().contradiction_autorun:
            try:
                contradiction_job = await JobRepository(conn).create(
                    user_id,
                    "detect_contradictions",
                    payload={
                        "concept_id": str(result.edge.concept_id),
                        "claim_id": str(result.edge.claim_id),
                    },
                )
                detect_contradictions.send(
                    str(result.edge.concept_id),
                    str(result.edge.claim_id),
                    user_id,
                    str(contradiction_job.id),
                )
            except Exception as exc:
                logger.warning(
                    "failed to auto-enqueue detect_contradictions for claim %s: %s",
                    result.edge.claim_id,
                    exc,
                )
    return {
        "concept": concept_dict,
        "edge": serialize_edge(result.edge),
    }
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/backend/test_claims_api.py -v`
Expected: all pass.

- [ ] **Step 9: Run the full backend/kernel/worker suite**

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

- [ ] **Step 10: Lint and type-check**

Run: `.venv/bin/ruff check kernel backend worker tests && .venv/bin/mypy kernel backend worker`
Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add worker/tasks/extract_claims.py backend/app/api/claims.py \
  tests/worker/test_extract_claims.py tests/backend/test_claims_api.py
git commit -m "feat: auto-enqueue contradiction detection after candidate approval"
```

---

### Task 5: API — expose and classify contradictions

**Files:**
- Create: `backend/app/api/contradictions.py`
- Modify: `backend/app/main.py` (register the router)
- Create: `tests/backend/test_contradictions_api.py`

**Interfaces:**
- Produces: `GET /contradictions?concept_id=&classification=&limit=&offset=`; `GET /contradictions/count?concept_id=&classification=`; `POST /contradictions/{id}/classify` (body `{"classification": str}`).
- Consumes: `kernel.db.contradictions.ContradictionRepository`/`CLASSIFICATIONS` (Task 1); `backend.app.api.concepts.serialize_claim` (existing); `kernel.db.claims.ClaimRepository` (existing).

- [ ] **Step 1: Write the failing API tests**

Create `tests/backend/test_contradictions_api.py`:

```python
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


async def _seed_contradiction(conn, user_id, source_id):  # type: ignore[no-untyped-def]
    concept = await ConceptRepository(conn).find_or_create(
        user_id=user_id, concept_type="idea", concept_name="Weather", description=None
    )
    claim_repo = ClaimRepository(conn)
    candidate_repo = ConceptCandidateRepository(conn)
    edge_repo = ClaimConceptEdgeRepository(conn)
    claims = []
    for text_ in ["It rained.", "It was sunny."]:
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": text_}], source_id, user_id
        )
        claim = await claim_repo.create(
            user_id=user_id,
            source_id=source_id,
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
            source_id=source_id,
            claim_id=claim.id,
            candidate_name="Weather",
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
        similarity=0.82,
        rationale="Both claims describe the same day's weather but disagree.",
    )
    assert contradiction is not None
    return concept, claims, contradiction


@pytest.mark.asyncio
async def test_list_contradictions_returns_both_claims_inline(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-1")
        concept, claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.get("/contradictions", params={"concept_id": str(concept.id)})

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == str(contradiction.id)
    assert body[0]["classification"] == "unresolved"
    assert {body[0]["claim_a"]["claim_text"], body[0]["claim_b"]["claim_text"]} == {
        "It rained.",
        "It was sunny.",
    }

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_contradictions_count_and_filter_by_classification(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-2")
        concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    before = await client.get(
        "/contradictions/count", params={"concept_id": str(concept.id), "classification": "unresolved"}
    )
    empty = await client.get(
        "/contradictions", params={"concept_id": str(concept.id), "classification": "evolution"}
    )

    assert before.json() == {"total": 1}
    assert empty.json() == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_updates_it(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-3")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "evolution"}
    )

    assert r.status_code == 200
    body = r.json()
    assert body["classification"] == "evolution"
    assert body["classified_at"] is not None

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_rejects_invalid_classification(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-4")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "not-a-real-value"}
    )

    assert r.status_code == 422

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_404s_when_not_found(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/contradictions/00000000-0000-0000-0000-000000000000/classify",
        json={"classification": "evolution"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/backend/test_contradictions_api.py -v`
Expected: FAIL — `404 Not Found` for all requests (no `/contradictions` router registered yet).

- [ ] **Step 3: Implement `backend/app/api/contradictions.py`**

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


class ClassifyBody(BaseModel):
    classification: str


async def _serialize_contradiction(
    contradiction: Contradiction, claims: ClaimRepository
) -> dict[str, Any] | None:
    claim_a = await claims.get(contradiction.claim_a_id)
    claim_b = await claims.get(contradiction.claim_b_id)
    if claim_a is None or claim_b is None:
        return None
    return {
        "id": str(contradiction.id),
        "concept_id": str(contradiction.concept_id),
        "claim_a": serialize_claim(claim_a),
        "claim_b": serialize_claim(claim_b),
        "similarity": contradiction.similarity,
        "classification": contradiction.classification,
        "rationale": contradiction.rationale,
        "created_at": contradiction.created_at.isoformat(),
        "classified_at": contradiction.classified_at.isoformat()
        if contradiction.classified_at
        else None,
    }


@router.get("/contradictions")
async def list_contradictions(
    concept_id: str | None = None,
    classification: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        contradictions = await ContradictionRepository(conn).list(
            concept_id=concept_id,
            classification=classification,
            limit=limit,
            offset=offset,
        )
        claims = ClaimRepository(conn)
        result = []
        for contradiction in contradictions:
            serialized = await _serialize_contradiction(contradiction, claims)
            if serialized is not None:
                result.append(serialized)
        return result


@router.get("/contradictions/count")
async def count_contradictions(
    concept_id: str | None = None,
    classification: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ContradictionRepository(conn).count(
            concept_id=concept_id, classification=classification
        )
    return {"total": total}


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

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, change:
```python
    app.include_router(claims.router)
    app.include_router(concepts.router)
    app.include_router(search.router)
```
to:
```python
    app.include_router(claims.router)
    app.include_router(concepts.router)
    app.include_router(contradictions.router)
    app.include_router(search.router)
```
and add `contradictions` to whatever import statement brings in `claims, concepts, search` at the top of that file (same module — `from backend.app.api import ...`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/backend/test_contradictions_api.py -v`
Expected: 5 passed

- [ ] **Step 6: Lint and type-check**

Run: `.venv/bin/ruff check backend tests && .venv/bin/mypy backend`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/contradictions.py backend/app/main.py tests/backend/test_contradictions_api.py
git commit -m "feat: add contradictions API"
```

---

### Task 6: Frontend — contradictions page

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `Contradiction`)
- Modify: `frontend/src/lib/api.ts` (add `listContradictions`, `getContradictionsCount`, `classifyContradiction`)
- Modify: `frontend/src/components/layout/NavIcon.tsx` (add a `"balance"` icon)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (add the nav entry)
- Create: `frontend/src/app/(app)/contradictions/page.tsx`
- Create: `frontend/src/app/(app)/contradictions/contradictions.test.tsx`

**Interfaces:**
- Produces: `Contradiction` TS type; `listContradictions`, `getContradictionsCount`, `classifyContradiction` API client functions; `/contradictions` page and nav link.
- Consumes: `backend/app/api/contradictions.py`'s endpoints (Task 5); `Claim` type, `Badge`/`Skeleton` components (existing).

- [ ] **Step 1: Write the failing frontend test**

Create `frontend/src/app/(app)/contradictions/contradictions.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, vi, describe, it, beforeEach } from "vitest"
import { ThemeProvider } from "@/lib/theme"
import type { Contradiction } from "@/lib/types"
import ContradictionsPage from "./page"

vi.mock("@/lib/api", () => ({
  listContradictions: vi.fn(),
  getContradictionsCount: vi.fn().mockResolvedValue(0),
  classifyContradiction: vi.fn(),
}))

import { classifyContradiction, getContradictionsCount, listContradictions } from "@/lib/api"
const mockListContradictions = vi.mocked(listContradictions)
const mockGetContradictionsCount = vi.mocked(getContradictionsCount)
const mockClassifyContradiction = vi.mocked(classifyContradiction)

function makeContradiction(overrides: Partial<Contradiction> = {}): Contradiction {
  return {
    id: "c1",
    conceptId: "concept-1",
    claimA: {
      id: "claim-a",
      sourceId: "src-1",
      observationId: "obs-1",
      claimText: "It rained.",
      claimType: "fact",
      assertionType: "reality",
      confidence: 0.9,
      extractionMethod: "llm",
      modelName: null,
      promptVersion: null,
      status: "proposed",
      createdAt: "2024-05-12T14:32:01Z",
    },
    claimB: {
      id: "claim-b",
      sourceId: "src-1",
      observationId: "obs-2",
      claimText: "It was sunny.",
      claimType: "fact",
      assertionType: "reality",
      confidence: 0.9,
      extractionMethod: "llm",
      modelName: null,
      promptVersion: null,
      status: "proposed",
      createdAt: "2024-05-12T14:32:01Z",
    },
    similarity: 0.82,
    classification: "unresolved",
    rationale: "Both claims describe the same day's weather but disagree.",
    createdAt: "2024-05-12T14:32:01Z",
    classifiedAt: null,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ThemeProvider>
      <ContradictionsPage />
    </ThemeProvider>,
  )
}

describe("ContradictionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetContradictionsCount.mockResolvedValue(0)
  })

  it("loads and shows both claims side by side with the rationale", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction()])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
      expect(screen.getByText("It was sunny.")).toBeInTheDocument()
      expect(screen.getByText(/disagree/)).toBeInTheDocument()
    })
  })

  it("filters by classification", async () => {
    const unresolved = makeContradiction({ id: "c1", classification: "unresolved" })
    const resolved = makeContradiction({
      id: "c2",
      classification: "evolution",
      claimA: { ...unresolved.claimA, claimText: "resolved claim a" },
      claimB: { ...unresolved.claimB, claimText: "resolved claim b" },
    })
    mockListContradictions.mockResolvedValueOnce([unresolved, resolved])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
      expect(screen.getByText("resolved claim a")).toBeInTheDocument()
    })

    const filterGroup = screen.getByRole("group", { name: "Filter by classification" })
    await userEvent.click(within(filterGroup).getByRole("button", { name: "evolution" }))

    expect(screen.queryByText("It rained.")).not.toBeInTheDocument()
    expect(screen.getByText("resolved claim a")).toBeInTheDocument()
  })

  it("classifies an unresolved contradiction and updates it in place", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction()])
    mockClassifyContradiction.mockResolvedValueOnce(
      makeContradiction({ classification: "true_conflict", classifiedAt: "2024-05-12T15:00:00Z" })
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
    })

    const row = screen.getByRole("article")
    await userEvent.click(within(row).getByRole("button", { name: "true_conflict" }))

    await waitFor(() => {
      expect(mockClassifyContradiction).toHaveBeenCalledWith("c1", "true_conflict")
    })
  })

  it("hides classify actions once a contradiction is already resolved", async () => {
    mockListContradictions.mockResolvedValueOnce([makeContradiction({ classification: "both" })])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("It rained.")).toBeInTheDocument()
    })

    const row = screen.getByRole("article")
    expect(within(row).queryByRole("button", { name: "true_conflict" })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run "src/app/(app)/contradictions/contradictions.test.tsx"`
Expected: FAIL — module `./page` doesn't exist.

- [ ] **Step 3: Add the `Contradiction` type**

In `frontend/src/lib/types.ts`, add after the `SearchResult` interface:

```ts
export interface Contradiction {
  id: string
  conceptId: string
  claimA: Claim
  claimB: Claim
  similarity: number
  classification: string
  rationale: string
  createdAt: string
  classifiedAt: string | null
}
```

- [ ] **Step 4: Add the API client functions**

In `frontend/src/lib/api.ts`, add `Contradiction` to the type import list at the top — change:
```ts
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
  SearchResult,
  Source,
  SourceType,
} from "./types"
```

Add at the end of the file (after `embedClaims`):

```ts
function toContradiction(d: Record<string, unknown>): Contradiction {
  return {
    id: String(d.id),
    conceptId: String(d.concept_id),
    claimA: toClaim(d.claim_a as Record<string, unknown>),
    claimB: toClaim(d.claim_b as Record<string, unknown>),
    similarity: Number(d.similarity),
    classification: String(d.classification),
    rationale: String(d.rationale),
    createdAt: String(d.created_at),
    classifiedAt: (d.classified_at as string | null) ?? null,
  }
}

export interface ContradictionQuery {
  conceptId?: string
  classification?: string
  limit?: number
  offset?: number
}

export async function listContradictions(q: ContradictionQuery = {}): Promise<Contradiction[]> {
  const params = new URLSearchParams()
  if (q.conceptId) params.set("concept_id", q.conceptId)
  if (q.classification) params.set("classification", q.classification)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/contradictions?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listContradictions failed")
  return (await r.json()).map(toContradiction)
}

export async function getContradictionsCount(
  q: Pick<ContradictionQuery, "conceptId" | "classification"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.conceptId) params.set("concept_id", q.conceptId)
  if (q.classification) params.set("classification", q.classification)
  const r = await req(`/contradictions/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getContradictionsCount failed")
  return Number((await r.json()).total ?? 0)
}

export async function classifyContradiction(
  contradictionId: string,
  classification: string
): Promise<Contradiction> {
  const r = await req(`/contradictions/${contradictionId}/classify`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ classification }),
  })
  if (!r.ok) throw await readError(r, "classifyContradiction failed")
  return toContradiction(await r.json())
}
```

- [ ] **Step 5: Add the nav icon and sidebar entry**

In `frontend/src/components/layout/NavIcon.tsx`, add `"balance"` to the `IconName` union — change:
```ts
export type IconName =
  | "dashboard"
  | "inventory_2"
  | "database"
  | "visibility"
  | "analytics"
  | "hub"
  | "search"
  | "orbit"
  | "toggle_off"
  | "toggle_on"
```
to:
```ts
export type IconName =
  | "dashboard"
  | "inventory_2"
  | "database"
  | "visibility"
  | "analytics"
  | "hub"
  | "balance"
  | "search"
  | "orbit"
  | "toggle_off"
  | "toggle_on"
```

Add the icon to the `ICONS` map, right after `hub`:
```tsx
  balance: (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="3" x2="12" y2="21" />
      <line x1="5" y1="7" x2="19" y2="7" />
      <path d="M5 7l-3 6a3 3 0 0 0 6 0z" />
      <path d="M19 7l-3 6a3 3 0 0 0 6 0z" />
      <line x1="9" y1="21" x2="15" y2="21" />
    </svg>
  ),
```

In `frontend/src/components/layout/Sidebar.tsx`, change:
```ts
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", pageTitle: "Archive Overview", href: "/dashboard", icon: "dashboard" },
  { label: "Import", href: "/import", icon: "inventory_2" },
  { label: "Sources", href: "/sources", icon: "database" },
  { label: "Observations", href: "/observations", icon: "visibility" },
  { label: "Claims", href: "/claims", icon: "analytics" },
  { label: "Concepts", href: "/concepts", icon: "hub" },
  { label: "Search", href: "/search", icon: "search" },
  { label: "Jobs", href: "/jobs", icon: "orbit" },
]
```
to:
```ts
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", pageTitle: "Archive Overview", href: "/dashboard", icon: "dashboard" },
  { label: "Import", href: "/import", icon: "inventory_2" },
  { label: "Sources", href: "/sources", icon: "database" },
  { label: "Observations", href: "/observations", icon: "visibility" },
  { label: "Claims", href: "/claims", icon: "analytics" },
  { label: "Concepts", href: "/concepts", icon: "hub" },
  { label: "Contradictions", href: "/contradictions", icon: "balance" },
  { label: "Search", href: "/search", icon: "search" },
  { label: "Jobs", href: "/jobs", icon: "orbit" },
]
```

- [ ] **Step 6: Implement the page**

Create `frontend/src/app/(app)/contradictions/page.tsx`:

```tsx
"use client"

import { useEffect, useMemo, useState } from "react"
import { classifyContradiction, getContradictionsCount, listContradictions } from "@/lib/api"
import type { Contradiction } from "@/lib/types"
import { Badge } from "@/components/ui/Badge"
import { Skeleton } from "@/components/ui/Skeleton"

const CLASSIFICATIONS = [
  "ALL",
  "unresolved",
  "true_conflict",
  "evolution",
  "contextual_difference",
  "both",
] as const

const CLASSIFY_ACTIONS = ["true_conflict", "evolution", "contextual_difference", "both"] as const

const PAGE_SIZE = 100

export default function ContradictionsPage() {
  const [contradictions, setContradictions] = useState<Contradiction[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [classification, setClassification] = useState("ALL")
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([listContradictions({ limit: PAGE_SIZE, offset: 0 }), getContradictionsCount()])
      .then(([data, count]) => {
        if (!cancelled) {
          setContradictions(data)
          setTotal(count)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load contradictions")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hasMore = contradictions !== null && total !== null && contradictions.length < total

  async function loadMore() {
    if (loadingMore || !hasMore || contradictions === null) return
    setLoadingMore(true)
    try {
      const data = await listContradictions({ limit: PAGE_SIZE, offset: contradictions.length })
      setContradictions((prev) => [...(prev ?? []), ...data])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load contradictions")
    } finally {
      setLoadingMore(false)
    }
  }

  async function handleClassify(id: string, value: string) {
    try {
      const updated = await classifyContradiction(id, value)
      setContradictions((prev) => (prev ?? []).map((c) => (c.id === id ? updated : c)))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to classify contradiction")
    }
  }

  const isLoading = contradictions === null && error === null
  const filtered = useMemo(() => {
    if (!contradictions) return []
    return contradictions.filter(
      (c) => classification === "ALL" || c.classification === classification
    )
  }, [contradictions, classification])

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-medium text-ink">Contradictions</h1>
          {contradictions !== null && total !== null && (
            <span className="rounded-meridian border border-hairline bg-surface px-2 py-0.5 font-mono text-xs text-accent">
              {contradictions.length < total ? `${contradictions.length} of ${total}` : total}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by classification">
        {CLASSIFICATIONS.map((item) => (
          <button
            aria-pressed={classification === item}
            className={
              classification === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setClassification(item)}
            type="button"
          >
            {item === "ALL" ? "All" : item}
          </button>
        ))}
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-hearth border border-hairline bg-surface px-6 py-4 text-sm text-muted"
        >
          Could not load contradictions: {error}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton className="h-24" key={index} />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-hairline border-y border-hairline">
          {filtered.map((c) => (
            <article className="space-y-3 py-4" key={c.id}>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-ink">{c.claimA.claimText}</p>
                  <Badge className="font-mono uppercase">{c.claimA.assertionType}</Badge>
                </div>
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-ink">{c.claimB.claimText}</p>
                  <Badge className="font-mono uppercase">{c.claimB.assertionType}</Badge>
                </div>
              </div>
              <p className="text-sm text-muted">{c.rationale}</p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="font-mono uppercase">{c.classification}</Badge>
                {c.classification === "unresolved" &&
                  CLASSIFY_ACTIONS.map((action) => (
                    <button
                      className="rounded-meridian border border-hairline px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
                      key={action}
                      onClick={() => handleClassify(c.id, action)}
                      type="button"
                    >
                      {action}
                    </button>
                  ))}
              </div>
            </article>
          ))}
          {filtered.length === 0 && error === null ? (
            <p className="py-8 text-sm text-muted">No contradictions match this filter.</p>
          ) : null}
        </div>
      )}

      {hasMore && contradictions !== null && error === null && (
        <button
          className="rounded-meridian bg-ember px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors hover:opacity-90 disabled:opacity-50"
          disabled={loadingMore}
          onClick={loadMore}
          type="button"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Run the tests, type-check, and lint**

Run:
```bash
cd frontend
npx vitest run "src/app/(app)/contradictions/contradictions.test.tsx"
npx tsc --noEmit
npx eslint src
```
Expected: all pass, no type errors, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/lib/types.ts" "frontend/src/lib/api.ts" \
  "frontend/src/components/layout/NavIcon.tsx" "frontend/src/components/layout/Sidebar.tsx" \
  "frontend/src/app/(app)/contradictions/page.tsx" \
  "frontend/src/app/(app)/contradictions/contradictions.test.tsx"
git commit -m "feat: add contradictions page to the frontend"
```

---

### Task 7: Docs

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: no code — documentation and env-var wiring only.

- [ ] **Step 1: Add the new env vars**

In `.env.example`, change:
```
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_AUTORUN=false
EMBEDDING_BATCH_SIZE=100
```
to:
```
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_AUTORUN=false
EMBEDDING_BATCH_SIZE=100
OPENAI_CONTRADICTION_MODEL=gpt-4o-mini
CONTRADICTION_CANDIDATE_LIMIT=5
CONTRADICTION_SIMILARITY_FLOOR=0.75
CONTRADICTION_AUTORUN=false
```

In `docker-compose.yml`, there are two occurrences of the embedding block (backend service and worker service) — change each:
```yaml
      OPENAI_EMBEDDING_MODEL: ${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}
      EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-1536}
      EMBEDDING_AUTORUN: ${EMBEDDING_AUTORUN:-false}
      EMBEDDING_BATCH_SIZE: ${EMBEDDING_BATCH_SIZE:-100}
```
to:
```yaml
      OPENAI_EMBEDDING_MODEL: ${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}
      EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-1536}
      EMBEDDING_AUTORUN: ${EMBEDDING_AUTORUN:-false}
      EMBEDDING_BATCH_SIZE: ${EMBEDDING_BATCH_SIZE:-100}
      OPENAI_CONTRADICTION_MODEL: ${OPENAI_CONTRADICTION_MODEL:-gpt-4o-mini}
      CONTRADICTION_CANDIDATE_LIMIT: ${CONTRADICTION_CANDIDATE_LIMIT:-5}
      CONTRADICTION_SIMILARITY_FLOOR: ${CONTRADICTION_SIMILARITY_FLOOR:-0.75}
      CONTRADICTION_AUTORUN: ${CONTRADICTION_AUTORUN:-false}
```
(both the `backend:` and `worker:` service blocks need this same addition).

- [ ] **Step 2: Add a README section**

In `README.md`, insert after the "Phase 2 Reality/Perception Separation" section (before "## Project Layout"):

```markdown
---

## Phase 2 Contradictions

Claims linked to the same concept are automatically checked for
contradictions when `CONTRADICTION_AUTORUN=true`: the claim's embedding
finds its most similar claims already linked to that concept (reusing the
Phase 1 Plan 3 embeddings), and each close-enough candidate pair gets one
LLM call deciding whether the two actually conflict. Confirmed pairs are
stored `unresolved` by default, per ADR-005 — the system never guesses
whether a contradiction is a true conflict, an evolution of understanding, a
contextual difference, or both.

`GET /api/contradictions` (filterable by `concept_id`/`classification`) and
`POST /api/contradictions/{id}/classify` let a user resolve one manually.
Custodian-assisted classification and concept revision tracking (the next
Phase 2 plan, which will consume `evolution`-classified contradictions) are
out of scope here; see
[docs/superpowers/specs/2026-07-09-contradictions-design.md](docs/superpowers/specs/2026-07-09-contradictions-design.md).

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

- [ ] **Step 4: Browser/API QA**

Start the stack (`docker compose up -d --build`), log in, and verify:
- Set `CONTRADICTION_AUTORUN=true`, upload a source with two observations that plainly conflict (e.g. "The meeting was moved to Friday." / "The meeting is still on Thursday."), extract claims, and confirm both claims land on the same concept and a contradiction appears at `GET /api/contradictions`.
- `/contradictions` shows both claim texts, the rationale, and the classify buttons; clicking one updates the row and removes the classify buttons.
- A second user never sees the first user's contradictions.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example docker-compose.yml
git commit -m "docs: document contradictions detection and classification"
```
