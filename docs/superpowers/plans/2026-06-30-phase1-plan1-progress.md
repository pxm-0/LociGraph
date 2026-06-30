# Phase 1 Plan 1 - Progress Ledger

Plan: `docs/superpowers/plans/2026-06-30-phase1-plan1-claim-extraction.md`
Branch: `codex/phase1-plan1-claim-extraction`
Base: `codex/phase0-plan4-frontend-deployment`

## Tasks

- Task 1: schema foundation - complete.
  - Migration, models, repositories, and initial tests added.
- Task 2: provider and worker - complete.
  - Provider abstraction and worker task added.
  - Auto-after-ingest wiring added.
- Task 3: API - complete.
  - Claims/candidates read APIs added.
  - Manual extraction endpoint added.
- Task 4: frontend - complete.
  - `/claims` route and source extraction controls added.
- Task 5: docs, review, publish - complete.
  - Ruff and mypy clean.
  - Pytest: 82 passed.
  - Frontend lint/build/typecheck clean.
  - Docker compose rebuild verified.
  - Impeccable detector passed.
  - Browser QA covered login, import, ingest, source extraction controls, safe extraction error handling, claims route, and mobile Claims layout.

## Notes

- Concept candidates remain proposed memory only.
- OpenAI is isolated behind a provider interface for later provider expansion.
- The configured local OpenAI key is invalid, so browser QA could not complete a successful live provider extraction. Worker/API success paths are covered with mocked-provider tests, and browser QA verified the safe failed-job path plus claims browsing against seeded QA rows.
