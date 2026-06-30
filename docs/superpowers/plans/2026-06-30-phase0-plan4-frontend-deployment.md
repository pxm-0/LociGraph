# Phase 0 - Plan 4: Frontend & Deployment Readiness

> **For agentic workers:** implement task-by-task, review each task, keep the
> progress ledger current, and gate final merge on backend, frontend, Docker,
> and browser QA checks.

## Goal

Land the missing Phase 0 frontend and single-origin deployment wiring so a user
can log in, import a source, poll ingestion, browse sources, and browse
observations before Phase 1 claims/concepts/graph begins.

## Architecture

Next.js 14 App Router lives in `frontend/` and talks to the existing FastAPI API
through relative `/api/*` paths with credentials included. Caddy remains the
single ingress: `/api/*` strips the prefix and proxies to backend, and all other
routes proxy to the frontend container.

## Tasks

- [x] Task 1: backend read support for frontend contracts.
- [x] Task 2: committed Next.js/Tailwind scaffold and typed API client.
- [x] Task 3: authenticated app shell, login, dashboard, import, sources, and
  observations routes.
- [x] Task 4: Docker/Caddy frontend deployment wiring and Docker context trim.
- [x] Task 5: focused backend tests and frontend build/lint/type gates.
- [ ] Task 6: browser QA through Caddy after Docker is available locally.

## Acceptance Criteria

- Login uses the real `/api/auth/login` cookie flow.
- Import submits real multipart uploads and polls `GET /api/jobs/{job_id}`.
- Dashboard, sources, and observations render real backend data.
- Backend routes remain tenant-scoped through `kernel.db.session(user_id)`.
- `ruff`, `mypy`, `pytest`, frontend lint, frontend typecheck, and frontend
  build pass in a provisioned environment.

## Out of Scope

No claims, concepts, graph, Custodian, Planetarium, AI extraction, or Method of
Loci work belongs in Plan 4.
