# Reality/Perception Separation — Design

## Summary
Phase 2, Plan 1 of the roadmap. Per ADR-002, reality and perception are
distinct: "a person stopped responding" (reality) is not the same object as
"this felt like abandonment" (perception). Claims already carry a
`claim_type` (`fact, event, belief, preference, definition, relationship,
emotion, interpretation, decision, task`) that partially encodes this
distinction but doesn't name it. This plan adds an explicit `assertion_type`
(`reality | perception | interpretation`) to every claim, classified by the
extraction LLM going forward and backfilled deterministically for existing
rows. This is groundwork for the Contradictions and Revisions plans that
follow — it does not implement either.

## Design

### Data model
Add `assertion_type TEXT NOT NULL` to `claims` via migration `0008`. No new
table — a concept aggregates claims of possibly mixed assertion types, so
the field lives on `Claim` only, not `Concept`. Validated in Python via an
`ASSERTION_TYPES = {"reality", "perception", "interpretation"}` set in
`kernel/ai/claim_extraction.py`, matching the existing `CLAIM_TYPES`
pattern — no DB `CHECK` constraint, consistent with how `claim_type` is
already unconstrained at the DB layer.

`kernel/models.py`'s `Claim` dataclass gains `assertion_type: str`, and
`Claim.from_row` reads it from `row["assertion_type"]`.

### Backfill
The same migration `0008` backfills every existing row using a deterministic
`claim_type → assertion_type` map, run once as a data migration (`UPDATE
claims SET assertion_type = CASE claim_type ... END`), then the column is
altered to `NOT NULL` (two-step: add nullable, backfill, set `NOT NULL`,
matching the standard safe-migration order for an existing table with rows).

There's no per-`claim_type` description anywhere in the codebase today (the
extraction prompt hands the LLM a bare enum, no definitions) — the mapping
below is grounded directly in ADR-002's three-way split (what happened /
what was felt / what was inferred), reasoned per type against how a personal
journaling/notes tool actually uses each label:

| claim_type | assertion_type | rationale |
|---|---|---|
| fact, event | reality | directly states something that is/was true or occurred |
| relationship, decision, task | reality | states an objective fact about the world or the person's recorded action/intent (a decision or task having been made/recorded is itself an event, regardless of what motivated it) |
| emotion, preference | perception | a felt/subjective state — the direct match for ADR-002's "this felt like abandonment" example |
| belief, interpretation | interpretation | an inferred conclusion or stance, not a raw fact or a felt state |
| definition | interpretation | in a personal notes context, defining a concept ("success means X to me") is the person's own conceptual framing, not an observed fact — closer to "what was inferred" than "what happened" |

This map is backfill-only — it never runs for newly-extracted claims, which
are always LLM-classified (see below). It's also inherently lossy (a
10-value enum collapsed into 3 buckets can't be perfectly accurate per-row),
so every row it touches gets `metadata["assertion_type_source"] =
"backfill_deterministic_v1"` set alongside the value (claims already store
free-form provenance in `metadata`, e.g. `{"raw": raw_claim}` from
extraction) — this makes backfilled labels distinguishable from
LLM-classified ones so a future pass can find and re-classify them if
accuracy ever turns out to matter, instead of silently blending two
different confidence levels under one column. A repository/migration test
asserts every value in `CLAIM_TYPES` has an entry in the backfill map, so
the map can't silently go stale if the claim_type taxonomy grows later.

### Extraction
`kernel/ai/claim_extraction.py`'s per-claim JSON schema gains a required
`assertion_type` field alongside `claim_type`, validated against
`ASSERTION_TYPES` the same way `claim_type` is validated against
`CLAIM_TYPES` (raise `ValueError` on an invalid value). `PROMPT_VERSION`
bumps from `claim-extraction-v1` to `claim-extraction-v2` since the model's
required output shape changes. `ExtractedClaim` (the dataclass the LLM
response is parsed into) gains `assertion_type: str`, and
`worker/tasks/extract_claims.py`'s call into `ClaimRepository.create` passes
it through.

### Repository
`ClaimRepository.create` gains an `assertion_type: str` parameter (required,
no default — every insert path already goes through the extraction worker,
which always has a value). `ClaimRepository.list` and `.count` gain an
`assertion_type: str | None = None` filter parameter, appended to the
`clauses`/`params` pattern identically to the existing `claim_type` filter.
`_COLUMNS` gains `assertion_type`.

### API
`GET /claims` and `GET /claims/count` (`backend/app/api/claims.py`) gain an
`assertion_type: str | None = None` query parameter, passed straight through
to the repository calls — same pattern as the existing `claim_type` param.
`serialize_claim` (`backend/app/api/concepts.py`) adds `"assertion_type":
claim.assertion_type` to its output dict.

### Frontend
`frontend/src/lib/types.ts`'s `Claim` type gains `assertionType: string`
(camelCase, matching how `claim_type` is already mapped to `claimType`).
`frontend/src/app/(app)/claims/page.tsx` — which today fetches all claims
and filters client-side via `useMemo` against a fixed `CLAIM_TYPES` pill
list — gets a second, parallel pill group (`ASSERTION_TYPES = ["ALL",
"reality", "perception", "interpretation"]`) wired into the same `filtered`
predicate (`matchesAssertion`), and each claim row's existing
`<Badge>{claim.claimType}</Badge>` gets a sibling `<Badge>` for
`claim.assertionType`. No new pages, no change to how claims are fetched
(server-side `assertion_type` API filter exists for future use but this
page doesn't need it, matching how it already ignores the server-side
`claim_type` filter today).

## Out of Scope
- Contradictions and Revisions — the next two Phase 2 plans, which will
  consume `assertion_type` but aren't implemented here.
- `assertion_type` on `Concept` — concepts aggregate claims of mixed types;
  giving a concept a single assertion_type is a modeling question for the
  Revisions plan, not this one.
- Multi-label assertion types (a claim being simultaneously reality and
  interpretation) — one value per claim, matching how `claim_type` already
  works.
- Re-extracting existing claims through the LLM to get a "real" classification
  instead of the deterministic backfill map — the backfill is a one-time
  best-effort label, not a claim of accuracy equal to LLM classification.
- Any Custodian involvement (Phase 3).
