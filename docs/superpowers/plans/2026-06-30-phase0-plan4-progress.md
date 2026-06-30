# Plan 4 - Frontend & Deployment Readiness - Progress Ledger

Plan: `docs/superpowers/plans/2026-06-30-phase0-plan4-frontend-deployment.md`
Branch: main working tree
Base: `016e0c3` (`origin/main`)

## Tasks

- Task 1: backend read support - complete.
  - `POST /sources/upload` returns `job_id`.
  - `GET /jobs/{job_id}` added for tenant-scoped polling.
  - Source responses include `imported_at` and `observation_count`.
  - `GET /dashboard/summary` added.
- Task 2: frontend scaffold/API client - complete.
  - Next.js 14 App Router, TypeScript, Tailwind, Geist/Outfit typography.
  - Typed relative API client with cookie credentials.
- Task 3: frontend screens - complete.
  - `/login`, `/dashboard`, `/import`, `/sources`, `/observations`.
  - Hearth/Meridian mode persisted via localStorage.
- Task 4: deployment wiring - complete.
  - `frontend/Dockerfile`, compose frontend service, Caddy frontend proxy.
  - `.dockerignore` added.
- Task 5: tests/gates - complete.
  - Ruff clean.
  - Mypy clean across 46 source files.
  - Pytest: 67 passed, 92% total coverage.
  - Frontend lint/typecheck/build clean.
  - Docker compose config and image build verified.
- Task 6: browser QA - complete.
  - Caddy `http://localhost` login verified.
  - Real upload performed through `/api/sources/upload`.
  - Worker completed ingest job.
  - Sources and observations rendered uploaded data.
  - Desktop and mobile screenshots checked; mobile Sources switched to card layout.

## Notes

- `docs/superpowers/specs/DESIGN.md` is the visual source of truth.
- Browser QA used the in-app Browser plugin against Caddy.
