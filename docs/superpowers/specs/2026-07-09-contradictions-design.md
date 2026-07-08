# Contradictions — Design

## Summary
Phase 2, Plan 2 of the roadmap (follows Reality/Perception Separation, precedes
Revisions). Per ADR-005, contradictions between claims are not auto-resolved —
they default to `unresolved` and a human classifies them later. This plan adds
detection (semantic-similarity-assisted, LLM-confirmed) and manual
classification for pairs of claims linked to the same concept. It is
groundwork for Revisions: a contradiction classified `evolution` is what a
future Revisions plan will consume to produce a concept's revision history.
Custodian-assisted classification (ADR-005's "assisted by the Custodian") is
explicitly out of scope — Custodian doesn't exist yet (Phase 3).

## Design

### Data model
New table `contradictions`, RLS-scoped exactly like every other table
(`ENABLE`/`FORCE ROW LEVEL SECURITY`, `<table>_user_isolation` policy, `GRANT`
to `locigraph_app`):

- `id, user_id, concept_id, claim_a_id, claim_b_id` — `claim_a_id`/`claim_b_id`
  reference `claims(id)`; `concept_id` references `concepts(id)`. Stored in a
  canonical order (`claim_a_id < claim_b_id` by UUID comparison) so a pair is
  never stored twice in reversed order.
- `similarity NUMERIC NOT NULL` — the cosine similarity that surfaced this
  pair as a detection candidate (kept for later tuning/debugging, not shown
  prominently in the UI).
- `classification TEXT NOT NULL DEFAULT 'unresolved'` — one field, not a
  separate status+classification pair. Valid values: `unresolved` (default),
  `true_conflict`, `evolution`, `contextual_difference`, `both`. No DB `CHECK`
  constraint, validated in Python — matches how `claim_type`/`assertion_type`
  are already validated at the application layer only.
- `rationale TEXT NOT NULL` — the LLM's explanation for why it flagged the
  pair, shown next to the claims in the UI so a user has context to classify.
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `classified_at
  TIMESTAMPTZ` (nullable, set when `classification` moves off `unresolved`).

A unique index on `(user_id, claim_a_id, claim_b_id)` prevents duplicate
detection from creating the same pair twice (the canonical ordering above is
what makes this index effective against reversed pairs too).

`kernel/models.py` gains a `Contradiction` dataclass (same
`frozen=True, slots=True` + `from_row` pattern as every other model).

### Detection: trigger
`approve_candidate` (`kernel/concepts_promotion.py`) has two existing
callers, and both need the same auto-enqueue added after it returns — kernel
functions stay pure (no worker/dramatiq dependency), so the side effect
belongs in each orchestrating caller, matching how `embed_claims` is already
auto-enqueued from *within* a worker task rather than from the kernel layer:

- **Primary path — `worker/tasks/extract_claims.py`'s auto-promotion loop**
  (`await approve_candidate(conn, created_candidate.id)`, currently
  unconditional: "at this volume, requiring a human to click approve on
  every single candidate isn't viable"). This is where nearly all candidates
  are promoted today, so it's the path that matters in practice.
- **Secondary path — `POST /concept-candidates/{id}/approve`**
  (`backend/app/api/claims.py`'s `approve_concept_candidate` endpoint), kept
  in sync for the rarer manual-approval path (e.g. a candidate a human
  re-approves after rejection).

Both call sites, after a successful `approve_candidate(...)` result, do the
same thing: create a `Job` row
(`JobRepository.create(user_id, "detect_contradictions", payload={"concept_id":
str(result.edge.concept_id), "claim_id": str(result.edge.claim_id)})`) then
`detect_contradictions.send(...)`, wrapped in a try/except that logs a
warning on failure rather than breaking extraction or the approval response
— identical failure-isolation shape to `embed_claims`'s existing auto-enqueue.
This keeps both call sites exactly as fast/synchronous as they are today;
contradictions appear moments later, the same UX pattern already established
for extraction/embedding jobs.

### Detection: worker task
New `worker/tasks/detect_contradictions.py`, actor signature
`detect_contradictions(concept_id: str, claim_id: str, user_id: str, job_id: str)`:

1. Load the new claim's embedding via `SemanticVectorRepository.get_for_claim`.
   If it doesn't exist yet (embedding is itself async/eventual — the claim may
   not have been embedded when this job runs), mark the job completed with
   `{"contradictions_found": 0, "skipped": "no_embedding_yet"}` and return. No
   retry loop in this plan — an acceptable, documented gap (see Out of Scope).
2. Find the top-N most similar *other* claims already linked to the same
   `concept_id` via a new `SemanticVectorRepository.search_similar_within_concept(concept_id, claim_id, query_embedding, limit)` — joins
   `semantic_vectors` → `claims` → `claim_concept_edges` filtered by
   `concept_id`, excludes `claim_id` itself, orders by cosine distance.
3. Drop any candidate below a similarity floor — both the candidate limit and
   floor come from a new `ContradictionSettings` dataclass (`from_env`, same
   pattern as `ClaimExtractionSettings`/`EmbeddingSettings`):
   `CONTRADICTION_CANDIDATE_LIMIT` (default `5`),
   `CONTRADICTION_SIMILARITY_FLOOR` (default `0.75`).
4. For each remaining pair, call a new `kernel/ai/contradiction_detection.py`
   (`OpenAIContradictionDetector`, same structured-output-JSON-schema pattern
   as `kernel/ai/claim_extraction.py`): input is both claims' `claim_text` and
   `assertion_type`; output is `{"is_contradiction": bool, "rationale": str}`.
   New env var `OPENAI_CONTRADICTION_MODEL` (default `gpt-4o-mini`, same
   default as extraction).
5. Insert an `unresolved` `contradictions` row for every pair where
   `is_contradiction` is true (`ContradictionRepository.create`, dedups via
   the unique index — `ON CONFLICT DO NOTHING`, matching every other
   repository's create method).
6. Mark the job completed with `{"contradictions_found": N}`.

**Reliability tolerances — mirror `extract_claims`/`embed_claims` exactly,
reusing their shared infrastructure rather than inventing new numbers:**
`@dramatiq.actor(queue_name="extraction", max_retries=3,
on_retry_exhausted="heal_detect_contradictions")` — same `max_retries=3` and
same `"extraction"` queue (same 25-thread worker process, no new concurrency
knob; there is no per-queue concurrency setting in this codebase today, just
`worker/Dockerfile`'s single `--threads 25` for the whole process). No custom
`time_limit` override — the job makes at most `CONTRADICTION_CANDIDATE_LIMIT`
(5) sequential LLM calls, comfortably inside dramatiq's default 10-minute
per-call limit, unlike `extract_claims`/`embed_claims` which need explicit
multi-hour overrides for genuinely long-running batches. A paired
`_heal_detect_contradictions`/`heal_detect_contradictions` actor reuses
`worker/tasks/healing.py`'s existing `next_heal_generation`/
`MAX_HEAL_GENERATIONS` (50)/`HEAL_DELAY_MS` (30s) — creates a fresh `Job` row
for the same `(concept_id, claim_id)` and re-sends with
`heal_generation=generation`, identical shape to `_heal_embed_claims`.
Detection is naturally idempotent for healing purposes: the `contradictions`
unique index means a healed retry that re-detects the same pair is a no-op
insert, not a duplicate. `MAX_OBSERVATIONS_PER_JOB`-style chunking doesn't
apply here — each job is already inherently bounded to at most 5 candidate
pairs by `CONTRADICTION_CANDIDATE_LIMIT`, so there's no unbounded-batch
problem to chunk away.

Register `detect_contradictions` and `heal_detect_contradictions` in
`worker/main.py` alongside the existing `extract_claims`/`embed_claims`
imports.

### API
`backend/app/api/contradictions.py` (new router):
- `GET /contradictions?concept_id=&classification=&limit=&offset=` — list,
  RLS-scoped like every other list endpoint, serializes both claims inline
  using the existing `serialize_claim` (`backend/app/api/concepts.py`) for
  `claim_a`/`claim_b` (`{"id", "concept_id", "claim_a": {...}, "claim_b":
  {...}, "similarity", "classification", "rationale", "created_at",
  "classified_at"}`) so the frontend doesn't need a second round-trip per
  row, and claim fields (including `assertion_type`) stay in lockstep with
  every other endpoint that returns a claim.
- `GET /contradictions/count?concept_id=&classification=`
- `POST /contradictions/{id}/classify` — body `{"classification": str}`,
  validated against the same enum as the DB column (excluding `unresolved`
  as a target — you classify *into* a resolution, you don't classify back
  into unresolved; reopening a contradiction is out of scope). 404 if not
  found or not visible to this tenant, 422 on an invalid classification
  value. Sets `classified_at = now()`.

### Frontend
New `/contradictions` page, mirroring `/claims`'s list+filter structure:
fetches paginated contradictions, a filter-pill group for `classification`
(`ALL`, `UNRESOLVED`, `TRUE_CONFLICT`, `EVOLUTION`, `CONTEXTUAL_DIFFERENCE`,
`BOTH`), each row shows both claim texts side by side with their
`assertion_type` badges (reusing the `Badge` component from the claims page),
the rationale text, and a classify action (a small button group for the four
non-`unresolved` values) that calls the classify endpoint and refreshes the
row in place. Added to the sidebar nav next to "Concepts".

## Out of Scope
- Custodian-assisted classification — Phase 3.
- LLM-suggested classification — this plan's LLM call only detects that a
  pair conflicts and explains why; it never proposes which of the four
  resolution categories applies. That judgment is entirely the user's.
- Cross-concept contradictions — only claims linked to the *same* concept are
  ever compared.
- Revisions — the next Phase 2 plan, which will consume `evolution`-classified
  contradictions.
- Retroactive rescanning — detection only runs going forward, triggered by
  new candidate approvals. Claim pairs already linked to a concept before
  this plan ships are never compared unless a future manual rescan endpoint
  is added; not needed today since concept usage so far is minimal.
- Retry/backoff for the "claim not embedded yet" case in worker step 1 — a
  known, narrow race (approval happening faster than the async embedding
  job) left as a documented gap rather than added machinery; revisit if it
  turns out to matter in practice.
- Reopening a resolved contradiction back to `unresolved`.
