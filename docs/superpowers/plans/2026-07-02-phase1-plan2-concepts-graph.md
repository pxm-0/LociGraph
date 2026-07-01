# Phase 1 - Plan 2: Canonical Concepts & Graph Foundation

## Summary
Promote proposed `concept_candidates` into a canonical `concepts` table with
an approve/reject flow, and add the first graph edges (`claim_concept_edges`)
connecting claims to the concepts they mention. Approval is a synchronous DB
operation, not an AI call: no new worker task. Do not build concept-to-concept
relationship inference or a node-link graph visualization in this plan.

## Task Briefs

### Task 1: schema foundation
- Add Alembic migration for RLS-protected `concepts` and `claim_concept_edges`,
  matching the `claims`/`concept_candidates` RLS/grant/index pattern from
  migration `0002`.
- `concepts`: canonical node — `id, user_id, concept_name, concept_type,
  description, status ('active' default), created_at, metadata`. Unique
  index on `(user_id, concept_type, lower(concept_name))` so promotion can
  dedup by exact case-insensitive name match within the same type.
- `claim_concept_edges`: graph edge — `id, user_id, claim_id, concept_id,
  concept_candidate_id, confidence, created_at`. Unique index on
  `(user_id, claim_id, concept_id)` — approving the same candidate twice
  must not duplicate the edge.
- Add model dataclasses (`Concept`, `ClaimConceptEdge`), repositories
  (`ConceptRepository`, `ClaimConceptEdgeRepository`), and tenant-isolation
  tests mirroring `tests/kernel/test_tenant_isolation.py`.

### Task 2: promotion logic
- `ConceptRepository.find_or_create(user_id, concept_type, concept_name, description)`:
  case-insensitive dedup lookup, insert on miss.
- `ConceptCandidateRepository` gains `approve(candidate_id)` and
  `reject(candidate_id)`, transitioning `status` `proposed -> accepted` /
  `proposed -> rejected`. Approving is idempotent: re-approving an already
  `accepted` candidate returns the existing concept + edge instead of
  erroring or duplicating.
- Approve path: within one transaction, find-or-create the concept, then
  insert the `claim_concept_edges` row referencing the candidate's
  `claim_id`. Reject path: status transition only, no concept or edge
  created.
- Unit tests: dedup across two candidates with the same name/type, reject
  leaves no concept/edge, idempotent re-approve, tenant isolation on
  approve/reject (cannot approve another user's candidate).

### Task 3: API
- Add `POST /concept-candidates/{candidate_id}/approve` and
  `POST /concept-candidates/{candidate_id}/reject`, 404 on missing/foreign
  candidate, 409 if the candidate is not in `proposed` status.
- Add `GET /concepts` (filterable by `concept_type`, `status`) and
  `GET /concepts/{concept_id}` — include a `claim_count` computed the same
  way `sources.py:serialize_source` computes `claim_count`, via a repository
  count method, not an inline query.
- Add `GET /concepts/{concept_id}/claims` returning the claims linked
  through `claim_concept_edges`, for the concept detail view.

### Task 4: frontend
- Add a "Review" section to `/claims` (or a new `/concepts` route — decide
  during implementation based on how crowded `/claims` gets) listing
  `proposed` concept candidates with Approve/Reject buttons, wired to the
  Task 3 endpoints, following the polling/optimistic-update pattern already
  used for extraction jobs in `sources/page.tsx`.
- Add a `/concepts` browse route: list canonical concepts with type badge
  and claim count, following the table conventions in `sources/page.tsx`
  and `SourceRow.tsx`.
- Preserve the accepted `DESIGN.md` Hearth/Meridian visual language. No
  graph/node-link rendering — this plan is list-based browsing only.

### Task 5: docs, review, publish
- Update README/docs to describe the promotion flow.
- Run backend/frontend gates (pytest, ruff, mypy, vitest, tsc) and Caddy
  browser QA covering approve, reject, idempotent re-approve, and the new
  `/concepts` route.
- Commit, push, and open a draft PR.

## Out of Scope
- Concept-to-concept relationships and inferred graph edges beyond
  claim-to-concept mentions.
- Interactive node-link graph visualization — deferred to the Planetarium
  (Phase 4). This plan only builds the underlying graph tables and a
  list-based browse UI.
- Editing or merging canonical concepts after creation (e.g. renaming,
  merging two duplicate concepts created under different capitalizations
  before the unique index existed).
- Embeddings / semantic search (Phase 1 Plan 3) and contradiction detection
  (Phase 2).
- Multi-provider extraction beyond the OpenAI implementation (carried over
  from Plan 1 — unchanged in this plan).
