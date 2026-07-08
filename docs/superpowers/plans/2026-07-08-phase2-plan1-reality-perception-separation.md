# Phase 2 Plan 1: Reality/Perception Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `assertion_type` (`reality | perception | interpretation`) to every claim — LLM-classified for new claims, deterministically backfilled for existing ones — per ADR-002's reality/perception separation, as groundwork for the Contradictions and Revisions plans that follow.

**Architecture:** A single new column on the existing `claims` table (no new table — a concept aggregates claims of mixed assertion types, so this lives on `Claim` only). Extraction, repository, API, and frontend each extend their existing `claim_type` handling with a parallel `assertion_type` field, following the exact same pattern already established for `claim_type` throughout the codebase.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (raw `text()` queries), asyncpg, Postgres 16, OpenAI structured outputs, Next.js/React/TypeScript, pytest + vitest.

## Global Constraints

- The next migration revision is `0008` (heads: `0001`→`0002`→`0003`→`0004`→`0005`→`0006`→`0007`).
- `assertion_type` is validated in Python only (an `ASSERTION_TYPES` set in `kernel/ai/claim_extraction.py`), no DB `CHECK` constraint — matches how `claim_type` is already validated today.
- `ClaimRepository.create` gains `assertion_type: str` as a **required** parameter with no default. Every test in the suite that calls `ClaimRepository(...).create(...)` directly (there are many, across `tests/backend/`, `tests/kernel/`, and `tests/worker/`) will raise `TypeError: create() missing 1 required keyword-only argument` until it passes one — fixing every one of these call sites is part of this plan, not a follow-up.
- All dataclasses use `@dataclass(frozen=True, slots=True)` with a `from_row(cls, row: Mapping[str, Any])` classmethod, matching every existing model in `kernel/models.py`.
- Design reference: `docs/superpowers/specs/2026-07-08-reality-perception-separation-design.md`.

---

### Task 1: Migration `0008` — `assertion_type` column and backfill

**Files:**
- Create: `migrations/versions/0008_assertion_type.py`

**Interfaces:**
- Produces: `claims.assertion_type TEXT NOT NULL` column, populated for every existing row.
- Consumes: nothing (pure schema/data migration).

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0008_assertion_type.py`:

```python
"""reality/perception separation — assertion_type on claims

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE claims ADD COLUMN assertion_type TEXT")
    op.execute(
        """
        UPDATE claims SET
            assertion_type = CASE claim_type
                WHEN 'fact' THEN 'reality'
                WHEN 'event' THEN 'reality'
                WHEN 'relationship' THEN 'reality'
                WHEN 'decision' THEN 'reality'
                WHEN 'task' THEN 'reality'
                WHEN 'emotion' THEN 'perception'
                WHEN 'preference' THEN 'perception'
                WHEN 'belief' THEN 'interpretation'
                WHEN 'interpretation' THEN 'interpretation'
                WHEN 'definition' THEN 'interpretation'
            END,
            metadata = metadata || '{"assertion_type_source": "backfill_deterministic_v1"}'::jsonb
        """
    )
    op.execute("ALTER TABLE claims ALTER COLUMN assertion_type SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE claims DROP COLUMN assertion_type")
```

This mapping covers all 10 `CLAIM_TYPES` values (see `kernel/ai/claim_extraction.py`). If a `claim_type` outside this set ever existed, the `CASE` would leave `assertion_type` `NULL` and the following `SET NOT NULL` would fail loudly — a safe failure, not a silent wrong default.

- [ ] **Step 2: Run the migration and verify it applies cleanly**

Run:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
.venv/bin/alembic upgrade head
```
Expected: no errors; `.venv/bin/alembic current` reports `0008`.

- [ ] **Step 3: Verify the backfill against real data**

Run:
```bash
docker exec locigraph-postgres-1 psql -U locigraph -d locigraph -c \
  "SELECT claim_type, assertion_type, metadata->>'assertion_type_source' AS source FROM claims;"
```
Expected: every row shows `assertion_type = reality` for `claim_type = fact` (the dev DB currently has 6 such rows), and `source = backfill_deterministic_v1` on all of them.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0008_assertion_type.py
git commit -m "feat: add assertion_type column to claims with reality/perception backfill"
```

---

### Task 2: Extraction — classify `assertion_type` for new claims

**Files:**
- Modify: `kernel/ai/claim_extraction.py`
- Modify: `tests/kernel/test_claim_extraction.py`
- Modify: `tests/worker/test_extract_claims.py`

**Interfaces:**
- Produces: `ASSERTION_TYPES: set[str]` (`{"reality", "perception", "interpretation"}`); `CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL: dict[str, str]` (documents the Task 1 migration's mapping, used only by a completeness-guard test below — never consulted at runtime); `ExtractedClaim.assertion_type: str`; `PROMPT_VERSION = "claim-extraction-v2"`.
- Consumes: nothing new — extends the existing `CLAIM_TYPES`/`_parse_claim`/`OpenAIClaimExtractor` machinery already in this file.

- [ ] **Step 1: Write the failing tests**

In `tests/kernel/test_claim_extraction.py`, change `_valid_claim` to include the new required field:

```python
def _valid_claim(observation_id: UUID, text: str = "a claim") -> dict:
    return {
        "observation_id": str(observation_id),
        "claim_text": text,
        "claim_type": "fact",
        "assertion_type": "reality",
        "confidence": 0.9,
        "concept_candidates": [],
    }
```

Add these two tests at the end of the file:

```python
def test_skips_claim_with_invalid_assertion_type_but_keeps_the_rest():
    obs_a, obs_b = uuid4(), uuid4()
    bad = _valid_claim(obs_a, "bad assertion type")
    bad["assertion_type"] = "not-a-real-type"
    payload = _payload([bad, _valid_claim(obs_b, "good claim")])
    result = _parse_extraction_payload(
        payload, {obs_a, obs_b}, extraction_method="test", model_name="m"
    )
    assert [c.claim_text for c in result.claims] == ["good claim"]


def test_backfill_map_covers_every_claim_type():
    from kernel.ai.claim_extraction import (
        ASSERTION_TYPES,
        CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL,
        CLAIM_TYPES,
    )

    assert set(CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL) == CLAIM_TYPES
    assert set(CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL.values()) <= ASSERTION_TYPES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/kernel/test_claim_extraction.py -v`
Expected: FAIL — `test_parses_valid_claims` and friends now error because `_parse_claim` doesn't recognize `assertion_type` yet (it's silently ignored, so the two new tests fail: `ImportError: cannot import name 'ASSERTION_TYPES'` for the last one, and the invalid-assertion_type test fails because nothing currently rejects it).

- [ ] **Step 3: Implement the `assertion_type` taxonomy and validation**

In `kernel/ai/claim_extraction.py`, add immediately after the `CLAIM_TYPES = {...}` block (before `CONCEPT_TYPES`):

```python
ASSERTION_TYPES = {"reality", "perception", "interpretation"}

# ponytail: backfill-only map mirroring migration 0008's SQL CASE statement —
# new claims are always LLM-classified via ASSERTION_TYPES above, never
# derived from this table. Kept here only so a test can assert every
# CLAIM_TYPES value has an entry, catching drift if the taxonomy grows.
CLAIM_TYPE_TO_ASSERTION_TYPE_BACKFILL: dict[str, str] = {
    "fact": "reality",
    "event": "reality",
    "relationship": "reality",
    "decision": "reality",
    "task": "reality",
    "emotion": "perception",
    "preference": "perception",
    "belief": "interpretation",
    "interpretation": "interpretation",
    "definition": "interpretation",
}
```

Bump the prompt version — change:
```python
PROMPT_VERSION = "claim-extraction-v1"
```
to:
```python
PROMPT_VERSION = "claim-extraction-v2"
```

Add `assertion_type` to `ExtractedClaim` (right after `claim_type`):
```python
@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    observation_id: UUID
    claim_text: str
    claim_type: str
    assertion_type: str
    confidence: float
    concept_candidates: list[ExtractedConceptCandidate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

In `_parse_claim`, add validation right after the existing `claim_type` check:
```python
    claim_type = str(raw_claim.get("claim_type", "")).strip()
    if claim_type not in CLAIM_TYPES:
        raise ValueError(f"invalid claim_type: {claim_type}")
    assertion_type = str(raw_claim.get("assertion_type", "")).strip()
    if assertion_type not in ASSERTION_TYPES:
        raise ValueError(f"invalid assertion_type: {assertion_type}")
```

And pass it through in the `return ExtractedClaim(...)` at the bottom of `_parse_claim`:
```python
    return ExtractedClaim(
        observation_id=observation_id,
        claim_text=claim_text,
        claim_type=claim_type,
        assertion_type=assertion_type,
        confidence=_as_float(raw_claim.get("confidence"), "confidence"),
        concept_candidates=candidates,
        metadata={"raw": raw_claim},
    )
```

- [ ] **Step 4: Update the LLM prompt and JSON schema**

In `OpenAIClaimExtractor.extract`, update the system message to instruct the model how to classify `assertion_type` — change:
```python
                    "content": (
                        "Extract atomic claims from observations. Return only claims "
                        "grounded in the supplied text. Suggest concept candidates as "
                        "non-canonical proposals. If an observation has no useful claim, "
                        "return no claim for it."
                    ),
```
to:
```python
                    "content": (
                        "Extract atomic claims from observations. Return only claims "
                        "grounded in the supplied text. Suggest concept candidates as "
                        "non-canonical proposals. If an observation has no useful claim, "
                        "return no claim for it. For each claim, also classify "
                        "assertion_type: 'reality' for something that happened or is "
                        "objectively true, 'perception' for a felt or subjective "
                        "experience (an emotion or preference), or 'interpretation' for "
                        "an inferred belief or conclusion drawn from reality."
                    ),
```

Update the JSON schema's `required` list and add the `assertion_type` property — change:
```python
                                    "required": [
                                        "observation_id",
                                        "claim_text",
                                        "claim_type",
                                        "confidence",
                                        "concept_candidates",
                                    ],
                                    "properties": {
                                        "observation_id": {"type": "string"},
                                        "claim_text": {"type": "string"},
                                        "claim_type": {
                                            "type": "string",
                                            "enum": sorted(CLAIM_TYPES),
                                        },
```
to:
```python
                                    "required": [
                                        "observation_id",
                                        "claim_text",
                                        "claim_type",
                                        "assertion_type",
                                        "confidence",
                                        "concept_candidates",
                                    ],
                                    "properties": {
                                        "observation_id": {"type": "string"},
                                        "claim_text": {"type": "string"},
                                        "claim_type": {
                                            "type": "string",
                                            "enum": sorted(CLAIM_TYPES),
                                        },
                                        "assertion_type": {
                                            "type": "string",
                                            "enum": sorted(ASSERTION_TYPES),
                                        },
```

- [ ] **Step 5: Fix the one other `ExtractedClaim(...)` construction in the test suite**

In `tests/worker/test_extract_claims.py`, `FakeExtractor.extract` constructs `ExtractedClaim` directly — change:
```python
                ExtractedClaim(
                    observation_id=observations[0].id,
                    claim_text=self.claim_text,
                    claim_type="fact",
                    confidence=0.88,
```
to:
```python
                ExtractedClaim(
                    observation_id=observations[0].id,
                    claim_text=self.claim_text,
                    claim_type="fact",
                    assertion_type="reality",
                    confidence=0.88,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_claim_extraction.py tests/worker/test_extract_claims.py -v`
Expected: all pass.

- [ ] **Step 7: Lint and type-check**

Run: `.venv/bin/ruff check kernel tests && .venv/bin/mypy kernel`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add kernel/ai/claim_extraction.py tests/kernel/test_claim_extraction.py tests/worker/test_extract_claims.py
git commit -m "feat: classify assertion_type during claim extraction"
```

---

### Task 3: Model + Repository — persist and filter `assertion_type`

**Files:**
- Modify: `kernel/models.py` (`Claim` dataclass)
- Modify: `kernel/db/claims.py` (`ClaimRepository.create`/`.list`/`.count`)
- Modify: `worker/tasks/extract_claims.py` (pass `extracted.assertion_type` through)
- Modify: `tests/kernel/test_claims_repository.py`
- Modify (mechanical — add `assertion_type=` to every `ClaimRepository(...).create(...)` call): `tests/backend/test_concepts_api.py`, `tests/backend/test_search_api.py`, `tests/backend/test_claims_api.py`, `tests/backend/test_dashboard_api.py`, `tests/backend/test_sources_api.py`, `tests/kernel/test_concepts_repository.py`, `tests/kernel/test_concepts_promotion.py`, `tests/kernel/test_semantic_vectors_repository.py`, `tests/kernel/test_tenant_isolation.py`, `tests/worker/test_embed_claims.py`

**Interfaces:**
- Produces: `Claim.assertion_type: str`; `ClaimRepository.create(..., assertion_type: str, ...)` (required); `ClaimRepository.list(..., assertion_type: str | None = None, ...)`; `ClaimRepository.count(..., assertion_type: str | None = None, ...)`.
- Consumes: `kernel.ai.claim_extraction.ExtractedClaim.assertion_type` (from Task 2).

- [ ] **Step 1: Write the failing repository test**

Add to `tests/kernel/test_claims_repository.py`:

```python
@pytest.mark.asyncio
async def test_list_and_count_filter_by_assertion_type(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "claims-assertion-filter")
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, user_id
        )
        repo = ClaimRepository(conn)
        reality_claim = await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_ids[0],
            claim_text="A fact happened.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await repo.create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_ids[1],
            claim_text="This felt difficult.",
            claim_type="emotion",
            assertion_type="perception",
            confidence=0.7,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

        filtered = await repo.list(source_id=source.id, assertion_type="reality")
        count = await repo.count(source_id=source.id, assertion_type="perception")

    assert reality_claim is not None
    assert reality_claim.assertion_type == "reality"
    assert [c.id for c in filtered] == [reality_claim.id]
    assert count == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/kernel/test_claims_repository.py::test_list_and_count_filter_by_assertion_type -v`
Expected: FAIL with `TypeError: create() got an unexpected keyword argument 'assertion_type'`.

- [ ] **Step 3: Add `assertion_type` to the `Claim` model**

In `kernel/models.py`, change the `Claim` dataclass — add `assertion_type: str` right after `claim_type: str`:

```python
@dataclass(frozen=True, slots=True)
class Claim:
    id: UUID
    user_id: UUID
    source_id: UUID
    observation_id: UUID
    claim_text: str
    claim_type: str
    assertion_type: str
    confidence: float
    extraction_method: str
    status: str
    created_at: datetime
    model_name: str | None = None
    prompt_version: str | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Claim:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            observation_id=row["observation_id"],
            claim_text=row["claim_text"],
            claim_type=row["claim_type"],
            assertion_type=row["assertion_type"],
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
            model_name=row.get("model_name"),
            prompt_version=row.get("prompt_version"),
            status=row["status"],
            created_at=row["created_at"],
            metadata=row.get("metadata"),
        )
```

- [ ] **Step 4: Add `assertion_type` to `ClaimRepository`**

In `kernel/db/claims.py`, change `_COLUMNS`:
```python
_COLUMNS = (
    "id, user_id, source_id, observation_id, claim_text, claim_type, assertion_type, "
    "confidence, extraction_method, model_name, prompt_version, status, created_at, metadata"
)
```

In `create`, add the parameter and wire it into the INSERT — change:
```python
    async def create(
        self,
        *,
        user_id: str | UUID,
        source_id: str | UUID,
        observation_id: str | UUID,
        claim_text: str,
        claim_type: str,
        confidence: float,
        extraction_method: str,
        model_name: str | None,
        prompt_version: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> Claim | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO claims
                        (user_id, source_id, observation_id, claim_text, claim_type,
                         confidence, extraction_method, model_name, prompt_version, metadata)
                    VALUES
                        (:user_id, :source_id, :observation_id, :claim_text, :claim_type,
                         :confidence, :extraction_method, :model_name, :prompt_version,
                         CAST(:metadata AS JSONB))
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_id": str(source_id),
                    "observation_id": str(observation_id),
                    "claim_text": strip_nul_bytes(claim_text),
                    "claim_type": claim_type,
                    "confidence": confidence,
                    "extraction_method": extraction_method,
                    "model_name": model_name,
                    "prompt_version": prompt_version,
                    "metadata": json.dumps(strip_nul_bytes(metadata or {})),
                },
            )
        ).mappings().first()
        return Claim.from_row(_as_mapping(row)) if row else None
```
to:
```python
    async def create(
        self,
        *,
        user_id: str | UUID,
        source_id: str | UUID,
        observation_id: str | UUID,
        claim_text: str,
        claim_type: str,
        assertion_type: str,
        confidence: float,
        extraction_method: str,
        model_name: str | None,
        prompt_version: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> Claim | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO claims
                        (user_id, source_id, observation_id, claim_text, claim_type,
                         assertion_type, confidence, extraction_method, model_name,
                         prompt_version, metadata)
                    VALUES
                        (:user_id, :source_id, :observation_id, :claim_text, :claim_type,
                         :assertion_type, :confidence, :extraction_method, :model_name,
                         :prompt_version, CAST(:metadata AS JSONB))
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_id": str(source_id),
                    "observation_id": str(observation_id),
                    "claim_text": strip_nul_bytes(claim_text),
                    "claim_type": claim_type,
                    "assertion_type": assertion_type,
                    "confidence": confidence,
                    "extraction_method": extraction_method,
                    "model_name": model_name,
                    "prompt_version": prompt_version,
                    "metadata": json.dumps(strip_nul_bytes(metadata or {})),
                },
            )
        ).mappings().first()
        return Claim.from_row(_as_mapping(row)) if row else None
```

In `list`, add the filter — change:
```python
    async def list(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Claim]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
```
to:
```python
    async def list(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        assertion_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Claim]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if assertion_type is not None:
            clauses.append("assertion_type = :assertion_type")
            params["assertion_type"] = assertion_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
```

In `count`, make the identical change — change:
```python
    async def count(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        status: str | None = None,
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
```
to:
```python
    async def count(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        assertion_type: str | None = None,
        status: str | None = None,
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if assertion_type is not None:
            clauses.append("assertion_type = :assertion_type")
            params["assertion_type"] = assertion_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
```

- [ ] **Step 5: Fix the existing `.create()` calls in this same test file**

`tests/kernel/test_claims_repository.py` has 6 pre-existing `.create()` calls that now need `assertion_type`. For each, insert the new line immediately after the line shown:

| Line (`claim_type=...`) | Insert immediately after |
|---|---|
| `claim_type="preference",` (in `test_claims_and_concept_candidates_round_trip`, ~line 25) | `assertion_type="perception",` |
| `"claim_type": "fact",` (in `test_claim_create_is_idempotent_for_live_text`'s `kwargs` dict, ~line 66) | `"assertion_type": "reality",` |
| `claim_type="fact",` (in `test_claim_and_candidate_create_strip_nul_bytes`, ~line 98) | `assertion_type="reality",` |
| `claim_type="fact",` (in `test_count_respects_filters`'s first `create`, ~line 139) | `assertion_type="reality",` |
| `claim_type="preference",` (in `test_count_respects_filters`'s second `create`, ~line 150) | `assertion_type="perception",` |
| `claim_type="fact",` (in `test_list_for_source_returns_every_claim_unpaginated`, ~line 181) | `assertion_type="reality",` |

- [ ] **Step 6: Run this file's tests to verify they pass**

Run: `.venv/bin/pytest tests/kernel/test_claims_repository.py -v`
Expected: all pass, including the new `test_list_and_count_filter_by_assertion_type`.

- [ ] **Step 7: Wire the worker's call site**

In `worker/tasks/extract_claims.py`, change:
```python
                    claim = await claim_repo.create(
                        user_id=user_id,
                        source_id=source_id,
                        observation_id=extracted.observation_id,
                        claim_text=extracted.claim_text,
                        claim_type=extracted.claim_type,
                        confidence=extracted.confidence,
                        extraction_method=result.extraction_method,
                        model_name=result.model_name,
                        prompt_version=result.prompt_version,
                        metadata=extracted.metadata,
                    )
```
to:
```python
                    claim = await claim_repo.create(
                        user_id=user_id,
                        source_id=source_id,
                        observation_id=extracted.observation_id,
                        claim_text=extracted.claim_text,
                        claim_type=extracted.claim_type,
                        assertion_type=extracted.assertion_type,
                        confidence=extracted.confidence,
                        extraction_method=result.extraction_method,
                        model_name=result.model_name,
                        prompt_version=result.prompt_version,
                        metadata=extracted.metadata,
                    )
```

- [ ] **Step 8: Fix every remaining `.create()` call site across the rest of the test suite**

Every other test file that calls `ClaimRepository(...).create(...)` (or `claim_repo.create(...)`) directly still needs `assertion_type` added, or it will fail with the same `TypeError`. For each row below, insert the new line immediately after the `claim_type=...,` line in that file:

| File | `claim_type=` value | Insert after it |
|---|---|---|
| `tests/backend/test_concepts_api.py` (~line 28) | `"preference"` | `assertion_type="perception",` |
| `tests/backend/test_search_api.py` (~line 47, `close_claim`) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_search_api.py` (~line 58, `far_claim`) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_search_api.py` (~line 117, hidden claim) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_claims_api.py` (~line 31) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_claims_api.py` (~line 83) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_claims_api.py` (~line 109, in the `for i, obs_id in enumerate(...)` loop) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_dashboard_api.py` (~line 30) | `"fact"` | `assertion_type="reality",` |
| `tests/backend/test_sources_api.py` (~line 308) | `"fact"` | `assertion_type="reality",` |
| `tests/kernel/test_concepts_repository.py` (~line 21) | `"preference"` | `assertion_type="perception",` |
| `tests/kernel/test_concepts_promotion.py` (~line 22) | `"preference"` | `assertion_type="perception",` |
| `tests/kernel/test_semantic_vectors_repository.py` (~line 24, in `_make_claim`) | `"fact"` | `assertion_type="reality",` |
| `tests/kernel/test_tenant_isolation.py` (~line 85) | `"fact"` | `assertion_type="reality",` |
| `tests/kernel/test_tenant_isolation.py` (~line 125) | `"fact"` | `assertion_type="reality",` |
| `tests/kernel/test_tenant_isolation.py` (~line 203) | `"fact"` | `assertion_type="reality",` |
| `tests/worker/test_embed_claims.py` (~line 44, in `_seed_claims`) | `"fact"` | `assertion_type="reality",` |

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
git add kernel/models.py kernel/db/claims.py worker/tasks/extract_claims.py \
  tests/kernel/test_claims_repository.py tests/backend/test_concepts_api.py \
  tests/backend/test_search_api.py tests/backend/test_claims_api.py \
  tests/backend/test_dashboard_api.py tests/backend/test_sources_api.py \
  tests/kernel/test_concepts_repository.py tests/kernel/test_concepts_promotion.py \
  tests/kernel/test_semantic_vectors_repository.py tests/kernel/test_tenant_isolation.py \
  tests/worker/test_embed_claims.py
git commit -m "feat: wire assertion_type through Claim model, repository, and worker"
```

---

### Task 4: API — expose and filter `assertion_type`

**Files:**
- Modify: `backend/app/api/claims.py` (`list_claims`, `count_claims`)
- Modify: `backend/app/api/concepts.py` (`serialize_claim`)
- Modify: `tests/backend/test_claims_api.py`

**Interfaces:**
- Produces: `GET /claims?assertion_type=...`, `GET /claims/count?assertion_type=...`; `serialize_claim(claim)` output gains `"assertion_type"`.
- Consumes: `ClaimRepository.list`/`.count`'s `assertion_type` filter (Task 3).

- [ ] **Step 1: Write the failing API test**

Add to `tests/backend/test_claims_api.py`:

```python
@pytest.mark.asyncio
async def test_claims_filter_by_assertion_type(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "claims-assertion-filter-api")
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, seeded_user
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_ids[0],
            claim_text="Fact claim.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_ids[1],
            claim_text="Preference claim.",
            claim_type="preference",
            assertion_type="perception",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.get(
        "/claims", params={"source_id": str(source.id), "assertion_type": "perception"}
    )

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["assertion_type"] == "perception"

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/backend/test_claims_api.py::test_claims_filter_by_assertion_type -v`
Expected: FAIL — `body[0]["assertion_type"]` raises `KeyError` (the field isn't serialized, and the query param is silently ignored so the filter doesn't narrow the results either).

- [ ] **Step 3: Implement the endpoint changes**

In `backend/app/api/claims.py`, change `list_claims` — from:
```python
@router.get("/claims")
async def list_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    return [serialize_claim(claim) for claim in claims]
```
to:
```python
@router.get("/claims")
async def list_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    assertion_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        claims = await ClaimRepository(conn).list(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            assertion_type=assertion_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    return [serialize_claim(claim) for claim in claims]
```

Change `count_claims` — from:
```python
@router.get("/claims/count")
async def count_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ClaimRepository(conn).count(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            status=status,
        )
    return {"total": total}
```
to:
```python
@router.get("/claims/count")
async def count_claims(
    source_id: str | None = None,
    observation_id: str | None = None,
    claim_type: str | None = None,
    assertion_type: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> dict[str, int]:
    async with session(user_id) as conn:
        total = await ClaimRepository(conn).count(
            source_id=source_id,
            observation_id=observation_id,
            claim_type=claim_type,
            assertion_type=assertion_type,
            status=status,
        )
    return {"total": total}
```

In `backend/app/api/concepts.py`, change `serialize_claim` — from:
```python
def serialize_claim(claim: Claim) -> dict[str, Any]:
    return {
        "id": str(claim.id),
        "source_id": str(claim.source_id),
        "observation_id": str(claim.observation_id),
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "extraction_method": claim.extraction_method,
        "model_name": claim.model_name,
        "prompt_version": claim.prompt_version,
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
    }
```
to:
```python
def serialize_claim(claim: Claim) -> dict[str, Any]:
    return {
        "id": str(claim.id),
        "source_id": str(claim.source_id),
        "observation_id": str(claim.observation_id),
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "assertion_type": claim.assertion_type,
        "confidence": claim.confidence,
        "extraction_method": claim.extraction_method,
        "model_name": claim.model_name,
        "prompt_version": claim.prompt_version,
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/backend/test_claims_api.py -v`
Expected: all pass, including `test_claims_filter_by_assertion_type`. (`GET /search`, in `backend/app/api/search.py`, reuses `serialize_claim` and automatically gains `assertion_type` too — no change needed there.)

- [ ] **Step 5: Lint and type-check**

Run: `.venv/bin/ruff check backend tests && .venv/bin/mypy backend`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/claims.py backend/app/api/concepts.py tests/backend/test_claims_api.py
git commit -m "feat: expose assertion_type in claims API"
```

---

### Task 5: Frontend — surface `assertion_type` on the claims page

**Files:**
- Modify: `frontend/src/lib/types.ts` (`Claim` interface)
- Modify: `frontend/src/lib/api.ts` (`toClaim`, `ClaimQuery`, `listClaims`, `getClaimsCount`)
- Modify: `frontend/src/app/(app)/claims/page.tsx`
- Modify: `frontend/src/app/(app)/claims/claims.test.tsx`

**Interfaces:**
- Produces: `Claim.assertionType: string`; `ClaimQuery.assertionType?: string`; a second filter-pill group and badge on the claims page.
- Consumes: `backend/app/api/claims.py`'s `assertion_type` field and query param (Task 4).

- [ ] **Step 1: Write the failing frontend test**

In `frontend/src/app/(app)/claims/claims.test.tsx`, update `makeClaims` to include the new field — change:
```tsx
function makeClaims(count: number, offset = 0): Claim[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `c${offset + i}`,
    sourceId: "src-1",
    observationId: "obs-1",
    claimText: `claim ${offset + i}`,
    claimType: "fact",
    confidence: 0.9,
    extractionMethod: "llm",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-05-12T14:32:01Z",
  }))
}
```
to:
```tsx
function makeClaims(count: number, offset = 0): Claim[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `c${offset + i}`,
    sourceId: "src-1",
    observationId: "obs-1",
    claimText: `claim ${offset + i}`,
    claimType: "fact",
    assertionType: "reality",
    confidence: 0.9,
    extractionMethod: "llm",
    modelName: null,
    promptVersion: null,
    status: "proposed",
    createdAt: "2024-05-12T14:32:01Z",
  }))
}
```

Add a new test inside the `describe("ClaimsPage", ...)` block:
```tsx
  it("filters by assertion type", async () => {
    const reality = { ...makeClaims(1)[0], id: "c-reality", claimText: "reality claim", assertionType: "reality" }
    const perception = {
      ...makeClaims(1)[0],
      id: "c-perception",
      claimText: "perception claim",
      assertionType: "perception",
    }
    mockListClaims.mockResolvedValueOnce([reality, perception])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText("reality claim")).toBeInTheDocument()
      expect(screen.getByText("perception claim")).toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole("button", { name: "perception" }))

    expect(screen.queryByText("reality claim")).not.toBeInTheDocument()
    expect(screen.getByText("perception claim")).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run "src/app/(app)/claims/claims.test.tsx"`
Expected: FAIL — `npx tsc --noEmit` (or the test itself) errors because `Claim` has no `assertionType` field yet, and there's no button named "perception".

- [ ] **Step 3: Add `assertionType` to the `Claim` type**

In `frontend/src/lib/types.ts`, change:
```ts
export interface Claim {
  id: string
  sourceId: string
  observationId: string
  claimText: string
  claimType: string
  confidence: number
  extractionMethod: string
  modelName: string | null
  promptVersion: string | null
  status: string
  createdAt: string
}
```
to:
```ts
export interface Claim {
  id: string
  sourceId: string
  observationId: string
  claimText: string
  claimType: string
  assertionType: string
  confidence: number
  extractionMethod: string
  modelName: string | null
  promptVersion: string | null
  status: string
  createdAt: string
}
```

- [ ] **Step 4: Wire it through the API client**

In `frontend/src/lib/api.ts`, change `toClaim`:
```ts
function toClaim(d: Record<string, unknown>): Claim {
  return {
    id: String(d.id),
    sourceId: String(d.source_id),
    observationId: String(d.observation_id),
    claimText: String(d.claim_text),
    claimType: String(d.claim_type),
    confidence: Number(d.confidence),
    extractionMethod: String(d.extraction_method),
    modelName: (d.model_name as string | null) ?? null,
    promptVersion: (d.prompt_version as string | null) ?? null,
    status: String(d.status),
    createdAt: String(d.created_at),
  }
}
```
to:
```ts
function toClaim(d: Record<string, unknown>): Claim {
  return {
    id: String(d.id),
    sourceId: String(d.source_id),
    observationId: String(d.observation_id),
    claimText: String(d.claim_text),
    claimType: String(d.claim_type),
    assertionType: String(d.assertion_type),
    confidence: Number(d.confidence),
    extractionMethod: String(d.extraction_method),
    modelName: (d.model_name as string | null) ?? null,
    promptVersion: (d.prompt_version as string | null) ?? null,
    status: String(d.status),
    createdAt: String(d.created_at),
  }
}
```

Change `ClaimQuery`, `listClaims`, and `getClaimsCount`:
```ts
export interface ClaimQuery {
  sourceId?: string
  observationId?: string
  claimType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listClaims(q: ClaimQuery = {}): Promise<Claim[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/claims?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listClaims failed")
  return (await r.json()).map(toClaim)
}

export async function getClaimsCount(
  q: Pick<ClaimQuery, "sourceId" | "observationId" | "claimType" | "status"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.status) params.set("status", q.status)
  const r = await req(`/claims/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getClaimsCount failed")
  return Number((await r.json()).total ?? 0)
}
```
to:
```ts
export interface ClaimQuery {
  sourceId?: string
  observationId?: string
  claimType?: string
  assertionType?: string
  status?: string
  limit?: number
  offset?: number
}

export async function listClaims(q: ClaimQuery = {}): Promise<Claim[]> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.assertionType) params.set("assertion_type", q.assertionType)
  if (q.status) params.set("status", q.status)
  if (q.limit != null) params.set("limit", String(q.limit))
  if (q.offset != null) params.set("offset", String(q.offset))
  const r = await req(`/claims?${params.toString()}`)
  if (!r.ok) throw await readError(r, "listClaims failed")
  return (await r.json()).map(toClaim)
}

export async function getClaimsCount(
  q: Pick<ClaimQuery, "sourceId" | "observationId" | "claimType" | "assertionType" | "status"> = {}
): Promise<number> {
  const params = new URLSearchParams()
  if (q.sourceId) params.set("source_id", q.sourceId)
  if (q.observationId) params.set("observation_id", q.observationId)
  if (q.claimType) params.set("claim_type", q.claimType)
  if (q.assertionType) params.set("assertion_type", q.assertionType)
  if (q.status) params.set("status", q.status)
  const r = await req(`/claims/count?${params.toString()}`)
  if (!r.ok) throw await readError(r, "getClaimsCount failed")
  return Number((await r.json()).total ?? 0)
}
```

- [ ] **Step 5: Add the pill filter and badge to the claims page**

In `frontend/src/app/(app)/claims/page.tsx`, add a new constant after `CLAIM_TYPES`:
```tsx
const ASSERTION_TYPES = ["ALL", "reality", "perception", "interpretation"] as const
```

Add state after `const [claimType, setClaimType] = useState("ALL")`:
```tsx
  const [assertionType, setAssertionType] = useState("ALL")
```

Update the `filtered` memo — change:
```tsx
  const filtered = useMemo(() => {
    if (!claims) return []
    const needle = query.trim().toLowerCase()
    return claims.filter((claim) => {
      const matchesType = claimType === "ALL" || claim.claimType === claimType
      const matchesQuery = needle === "" || claim.claimText.toLowerCase().includes(needle)
      return matchesType && matchesQuery
    })
  }, [claims, claimType, query])
```
to:
```tsx
  const filtered = useMemo(() => {
    if (!claims) return []
    const needle = query.trim().toLowerCase()
    return claims.filter((claim) => {
      const matchesType = claimType === "ALL" || claim.claimType === claimType
      const matchesAssertion = assertionType === "ALL" || claim.assertionType === assertionType
      const matchesQuery = needle === "" || claim.claimText.toLowerCase().includes(needle)
      return matchesType && matchesAssertion && matchesQuery
    })
  }, [claims, claimType, assertionType, query])
```

Add a second pill group right after the existing claim-type one (after its closing `</div>`, before the `{error !== null && (...)}` block):
```tsx
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by assertion type">
        {ASSERTION_TYPES.map((item) => (
          <button
            aria-pressed={assertionType === item}
            className={
              assertionType === item
                ? "rounded-meridian bg-ember px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-void transition-colors"
                : "rounded-meridian px-3 py-1.5 font-mono text-xs uppercase tracking-widest text-muted transition-colors hover:text-ink"
            }
            key={item}
            onClick={() => setAssertionType(item)}
            type="button"
          >
            {item === "ALL" ? "All" : item}
          </button>
        ))}
      </div>
```

Add a second badge to each row — change:
```tsx
              <div>
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
              </div>
```
to:
```tsx
              <div className="flex flex-wrap gap-1">
                <Badge className="font-mono uppercase">{claim.claimType}</Badge>
                <Badge className="font-mono uppercase">{claim.assertionType}</Badge>
              </div>
```

- [ ] **Step 6: Run the tests, type-check, and lint**

Run:
```bash
cd frontend
npx vitest run "src/app/(app)/claims/claims.test.tsx"
npx tsc --noEmit
npx eslint src
```
Expected: all pass, no type errors, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add "frontend/src/lib/types.ts" "frontend/src/lib/api.ts" "frontend/src/app/(app)/claims/page.tsx" "frontend/src/app/(app)/claims/claims.test.tsx"
git commit -m "feat: surface assertion_type in the claims page"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: no code — documentation only.

- [ ] **Step 1: Add a README section**

In `README.md`, insert after the "Phase 1 Embeddings & Semantic Search" section (before "## Project Layout"):

```markdown
---

## Phase 2 Reality/Perception Separation

Every claim carries an `assertion_type` (`reality`, `perception`, or
`interpretation`) alongside its existing `claim_type`, per ADR-002 — reality
and perception are modeled as distinct facets of a claim, not collapsed into
one label. New claims are classified by the extraction LLM; claims that
existed before this field was introduced were backfilled deterministically
from their `claim_type` and are tagged
`metadata.assertion_type_source = "backfill_deterministic_v1"` so they stay
distinguishable from LLM-classified claims.

`GET /api/claims` and `GET /api/claims/count` accept `?assertion_type=`
alongside the existing `?claim_type=` filter. Contradiction detection and
concept revision tracking — the next two Phase 2 plans — are out of scope
here; see
[docs/superpowers/specs/2026-07-08-reality-perception-separation-design.md](docs/superpowers/specs/2026-07-08-reality-perception-separation-design.md).

---
```

- [ ] **Step 2: Run the full gate one final time**

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

- [ ] **Step 3: Browser QA**

Start the stack (`docker compose up -d`, rebuilding backend/worker/frontend), log in, and verify:
- `/claims` shows a second badge per row for `assertion_type`, and the new pill filter narrows the list correctly.
- Existing claims (backfilled) show a plausible `assertion_type` — the dev DB's 6 `fact` claims should all show `reality`.
- A newly-extracted claim (trigger `POST /sources/{id}/extract-claims` on a fresh source) gets an LLM-classified `assertion_type`, not just `reality` by default.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document reality/perception separation"
```
