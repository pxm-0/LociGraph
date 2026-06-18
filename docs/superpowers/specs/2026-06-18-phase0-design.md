# Phase 0 Design Spec: Foundation, Ingestion & Source Lifecycle

**Date:** 2026-06-18  
**Project:** LociGraph  
**Scope:** Phase 0 — project scaffolding, auth, ingestion pipeline, source lifecycle, async workers, CI

---

## 1. Overview

Phase 0 delivers the structural foundation of LociGraph. No AI extraction, no claims, no concepts. The goal is a working pipeline that accepts raw source files and produces stored, queryable observations — with a real UI, real auth, a real async job queue, and a real CI pipeline.

**Deliverables:**
- Monorepo project structure
- Docker Compose (6 services: frontend, backend, worker, postgres, redis, caddy)
- PostgreSQL schema with RLS, pgvector, Alembic migrations
- JWT auth (single-user, multi-user ready)
- Source ingestion API + 6 format parsers
- Async job queue (Dramatiq + Redis)
- Next.js frontend: Login, Dashboard, Import, Sources, Observations
- GitHub Actions CI (PR checks + main branch push)

---

## 2. Project Structure

```
locigraph/
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router pages
│   │   │   ├── (auth)/     # Login page
│   │   │   ├── dashboard/
│   │   │   ├── import/
│   │   │   ├── sources/
│   │   │   └── observations/
│   │   ├── components/
│   │   │   ├── ui/         # Primitives (Button, Badge, Card, Input)
│   │   │   ├── layout/     # Sidebar, Orb, ModeToggle
│   │   │   └── domain/     # SourceRow, ObservationCard, StatusBadge
│   │   └── lib/
│   │       ├── api.ts      # Typed API client
│   │       └── auth.ts     # Token helpers
│   ├── public/
│   ├── tailwind.config.ts
│   └── package.json
│
├── backend/
│   └── app/
│       ├── api/
│       │   ├── auth.py     # POST /auth/login, POST /auth/logout
│       │   ├── sources.py  # POST /sources/upload, GET /sources, GET /sources/{id}
│       │   └── observations.py  # GET /observations
│       ├── auth/
│       │   ├── jwt.py      # Token creation + validation
│       │   └── middleware.py    # Request injection of current_user
│       ├── jobs/
│       │   └── submit.py   # Dramatiq task dispatch helpers
│       ├── main.py
│       └── config.py       # Settings from env
│
├── kernel/
│   ├── ingestion/
│   │   ├── base.py         # Parser protocol + Fragment dataclass
│   │   ├── json_parser.py
│   │   ├── pdf_parser.py
│   │   ├── html_parser.py
│   │   ├── markdown_parser.py
│   │   ├── chatgpt_parser.py
│   │   └── meta_parser.py
│   ├── normalizer.py       # Fragment → Observation
│   ├── models.py           # Domain dataclasses (Source, Fragment, Observation)
│   └── db/
│       ├── connection.py   # Connection factory, RLS session context
│       ├── sources.py      # SourceRepository
│       ├── fragments.py    # FragmentRepository
│       └── observations.py # ObservationRepository
│
├── worker/
│   ├── tasks/
│   │   └── ingest_source.py
│   └── main.py             # Dramatiq broker setup
│
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
│
├── .github/
│   └── workflows/
│       ├── pr.yml
│       └── main.yml
│
├── docker-compose.yml
├── Caddyfile
├── pyproject.toml          # Shared Python tooling config
└── .env.example
```

---

## 3. Docker Compose Services

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: locigraph
      POSTGRES_USER: locigraph
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  backend:
    build: ./backend
    depends_on: [postgres, redis]
    environment:
      # App connects as the NON-OWNER role so RLS is enforced (see §4).
      DATABASE_URL: postgresql+asyncpg://locigraph_app:${APP_DB_PASSWORD}@postgres:5432/locigraph
      # Owner role, used only for migrations.
      MIGRATION_DATABASE_URL: postgresql+asyncpg://locigraph:${POSTGRES_PASSWORD}@postgres:5432/locigraph
      REDIS_URL: redis://redis:6379
      JWT_SECRET: ${JWT_SECRET}
      LOCIGRAPH_PASSWORD: ${LOCIGRAPH_PASSWORD}

  worker:
    build: ./worker
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://locigraph_app:${APP_DB_PASSWORD}@postgres:5432/locigraph
      REDIS_URL: redis://redis:6379

  frontend:
    build: ./frontend
    depends_on: [backend]
    # API paths are relative (/api/*); Caddy (prod) / Next rewrites (dev) handle routing.

  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on: [backend, frontend]
```

**AWS migration path:** Each service maps 1:1 to an ECS Fargate task definition. Postgres → RDS, Redis → ElastiCache, file storage → S3 (add an S3 adapter to the storage layer). No schema changes required.

---

## 4. Database Schema

### Multi-Tenancy Model

**Row-level multi-tenancy with PostgreSQL RLS.** Every data table carries `user_id UUID NOT NULL REFERENCES users(id)`. The per-transaction setting `app.current_user_id` scopes every query. RLS policies filter all reads and writes on `current_setting('app.current_user_id')::uuid`.

**CRITICAL — two database roles (RLS owner-bypass fix):**
PostgreSQL does **not** enforce RLS against a table's owner by default. Therefore the application must **never** connect as the table owner.

- **`locigraph`** (owner) — owns all tables. Used **only** to run Alembic migrations. Never used by the app or workers.
- **`locigraph_app`** (non-owner) — granted `SELECT/INSERT/UPDATE/DELETE` on data tables, owns nothing. This is the role the backend and workers connect as. RLS is fully enforced against it.

The migration creates `locigraph_app`, grants table privileges, and grants `USAGE` on sequences. As belt-and-suspenders we also `FORCE ROW LEVEL SECURITY` on every data table so RLS holds even if a future connection accidentally uses the owner role.

**Transaction contract (why `SET LOCAL`):**
`SET LOCAL` is scoped to the current transaction and reset at COMMIT/ROLLBACK. This is mandatory for two reasons: (1) outside a transaction it is a no-op, leaving queries with no context; (2) with connection pooling, a plain session-level `SET` would leak the previous user's context to the next request that reuses the connection. Therefore: **every RLS-scoped query runs inside an explicit transaction, with `SET LOCAL app.current_user_id` as the first statement.** The `db.session(user_id)` context manager is the only way to obtain a scoped connection; there is no API to query outside this wrapper.

**Tenant isolation invariants:**
1. Every data table has `user_id` — no exceptions.
2. App and workers connect as `locigraph_app` (non-owner); `FORCE ROW LEVEL SECURITY` is set on every data table.
3. Every RLS-scoped query runs inside a transaction opened by `db.session(user_id)`, which issues `SET LOCAL app.current_user_id` first.
4. Kernel repositories require `user_id` as an explicit argument — no ambient context, no default.
5. `current_setting('app.current_user_id')` fails closed: if unset, the `::uuid` cast errors and the query is rejected rather than leaking data.
6. Audit logs always carry `actor_id = user_id`.
7. Integration tests connect as `locigraph_app` and include cross-tenant assertions (user A cannot read user B's rows).

### Tables (Phase 0)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sources
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    source_type TEXT NOT NULL,
    original_filename TEXT,
    original_mime_type TEXT,
    checksum_sha256 TEXT NOT NULL,
    file_size_bytes BIGINT,
    raw_storage_path TEXT,
    import_status TEXT NOT NULL DEFAULT 'PENDING',
    retention_policy TEXT NOT NULL DEFAULT 'standard',
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at TIMESTAMPTZ,
    purged_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    -- Enforce dedup at the DB level; app-level checks race under concurrent uploads.
    UNIQUE (user_id, checksum_sha256)
);

-- Fragments
CREATE TABLE fragments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    source_id UUID NOT NULL REFERENCES sources(id),
    raw_index INTEGER,
    raw_payload JSONB,
    extracted_text TEXT,
    timestamp TIMESTAMPTZ,
    author TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Observations
CREATE TABLE observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    source_id UUID REFERENCES sources(id),
    fragment_id UUID REFERENCES fragments(id),
    observed_at TIMESTAMPTZ,
    speaker TEXT,
    content TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    confidence NUMERIC NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'
);

-- Jobs
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 5,
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Audit logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    target_ref_type TEXT NOT NULL,
    target_ref_id UUID NOT NULL,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'
);
```

### App role + RLS Policies

```sql
-- Non-owner application role. Owns nothing → RLS is enforced against it.
CREATE ROLE locigraph_app LOGIN PASSWORD :'app_db_password';
GRANT SELECT, INSERT, UPDATE, DELETE ON sources, fragments, observations, jobs TO locigraph_app;
GRANT SELECT, INSERT ON audit_logs TO locigraph_app;
GRANT SELECT, INSERT, UPDATE ON users TO locigraph_app;  -- login + init only
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO locigraph_app;

-- Enable AND force RLS on every data table.
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources FORCE ROW LEVEL SECURITY;   -- holds even for the owner

-- USING governs read/update/delete visibility; WITH CHECK governs inserts/updates.
CREATE POLICY sources_user_isolation ON sources
    USING (user_id = current_setting('app.current_user_id')::uuid)
    WITH CHECK (user_id = current_setting('app.current_user_id')::uuid);
```

Same `ENABLE` + `FORCE` + policy (with both `USING` and `WITH CHECK`) on `fragments`, `observations`, `jobs`.

**Fail-closed:** `current_setting('app.current_user_id')` is called **without** the `missing_ok` flag. If the setting is unset, the `::uuid` cast raises and the query is rejected — no context means no data, never all data.

`users` and `audit_logs` have no RLS in Phase 0 — they are reached only through service-level functions (login, init_user, audit writes), never from user-driven queries. `audit_logs` RLS is revisited when a read endpoint is added (post-Phase 0).

### pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

`semantic_vectors` table deferred to Phase 1. Extension enabled in Phase 0 migration so it's available.

---

## 5. Auth

### Login flow

```
POST /auth/login  { password: string }
→ compare against bcrypt hash of LOCIGRAPH_PASSWORD env var
→ if match: create JWT { sub: user_id, exp: 7d }
→ set cookie "locigraph_token": HttpOnly; SameSite=Lax; Secure (prod); Path=/
→ return { user_id }

POST /auth/logout
→ clear cookie
```

**Same-origin (no CORS):** Both dev and prod serve frontend and API from one origin. Prod: Caddy routes `/api/*` → backend. Dev: Next.js `rewrites` proxy `/api/*` → `http://localhost:8000`. The browser only ever talks to the frontend origin, so the `HttpOnly; SameSite=Lax` cookie works identically in both — and there is no CORS configuration to get wrong.

**JWT middleware:** On every authenticated request, validate token from cookie, load user from DB, inject into `request.state.user`. Return `401` on missing or expired token.

**Initial user:** Created by a startup script (`python -m backend.scripts.init_user`) using `LOCIGRAPH_EMAIL` + `LOCIGRAPH_PASSWORD` env vars. Idempotent — no-op if user already exists.

**Multi-user readiness:** Adding a second user is a row insert into `users`. The registration endpoint is deferred but the schema is ready.

---

## 6. Ingestion Pipeline

### API

```
POST /sources/upload
  Content-Type: multipart/form-data
  Body: file (required)

→ validate mime type (allowed list)
→ stream upload to a temp file (avoid loading large exports fully into memory)
→ compute SHA-256 checksum
→ reject duplicate checksum (same user) — relies on UNIQUE (user_id, checksum_sha256)
→ move file to raw_storage_path (local volume in Phase 0, S3-swappable)
→ insert sources row (status: PENDING)
→ insert jobs row (job_type: ingest_source, status: pending) — canonical work ledger
→ enqueue ingest_source Dramatiq task with { source_id, user_id, job_id }
→ return 202 { source_id, status: "PENDING" }

GET /sources
→ list sources for current user (paginated, newest first)

GET /sources/{id}
→ single source with current status (used for polling)

GET /observations
→ paginated, filterable by source_id, speaker, status, date range
```

### Worker task

The kernel is async (SQLAlchemy 2.0 + asyncpg). Dramatiq actors are sync, so each task drives the async kernel with `asyncio.run(...)` — one event loop per execution. The sync `@dramatiq.actor` is a thin wrapper; all DB work lives in the async kernel.

```python
@dramatiq.actor(queue_name="ingestion", max_retries=3)
def ingest_source(source_id: str, user_id: str, job_id: str):
    asyncio.run(_ingest(source_id, user_id, job_id))


async def _ingest(source_id: str, user_id: str, job_id: str):
    # db.session opens a transaction and issues SET LOCAL app.current_user_id first.
    async with db.session(user_id) as s:                       # RLS-scoped txn
        await JobRepository(s).mark_running(job_id)
        await SourceRepository(s).set_status(source_id, "INGESTING")

    try:
        async with db.session(user_id) as s:
            source = await SourceRepository(s).get(source_id)
            parser = get_parser(source.source_type)            # router
            fragments = parser.parse(source.raw_storage_path)  # CPU/IO, no DB
            await FragmentRepository(s).bulk_insert(fragments, source_id, user_id)
            observations = Normalizer().normalize(fragments)
            await ObservationRepository(s).bulk_insert(observations, source_id, user_id)
            await SourceRepository(s).mark_verified(source_id)
            await JobRepository(s).mark_completed(job_id, result={"observations": len(observations)})
    except Exception as exc:
        # New session: the failed transaction is already rolled back.
        async with db.session(user_id) as s:
            await JobRepository(s).record_attempt(job_id, error=str(exc))
            if current_retry_exhausted():
                await SourceRepository(s).set_status(source_id, "FAILED")
        raise   # let Dramatiq apply retry/backoff
```

**Idempotency:** `ingest_source` is safe to re-run. Before inserting, it checks whether fragments/observations already exist for `source_id` and skips work that's done (covers Dramatiq retries after a partial failure).

**Failure model:** Dramatiq retries up to 3× with exponential backoff. Each attempt increments `jobs.attempts` and records the error. On final exhaustion, `sources.import_status → FAILED` and `jobs.status → failed`. The `jobs` row is the canonical async-work ledger; Redis only carries execution state.

### Source status transitions

```
PENDING → INGESTING → VERIFIED
                    → FAILED
VERIFIED → QUARANTINED (manual, future)
VERIFIED → PURGED (retention job, future)
```

### Format parsers

All parsers implement the `Parser` protocol:

```python
class Parser(Protocol):
    def parse(self, path: Path) -> list[Fragment]: ...
```

| Parser | Source type | Fragment unit |
|---|---|---|
| `json_parser` | Generic JSON | Top-level array item or root object |
| `pdf_parser` | PDF | Page (via `pdfplumber`) |
| `html_parser` | HTML | Block-level element (via `BeautifulSoup`) |
| `markdown_parser` | Markdown | Paragraph or section (via `mistune`) |
| `chatgpt_parser` | `conversations.json` | One message object (role + content + timestamp) |
| `meta_parser` | Meta JSON export | One message object (sender + content + timestamp) |

`chatgpt_parser` and `meta_parser` extract `author`/`speaker` and `timestamp` fields into Fragment. Other parsers extract what's available.

### Normalizer

`kernel/normalizer.py` converts `Fragment → Observation`. Rules:
- `content` = `fragment.extracted_text` (stripped, non-empty required)
- `observed_at` = `fragment.timestamp` (nullable)
- `speaker` = `fragment.author` (nullable)
- `context_before` / `context_after` = adjacent fragment text (window of 1)
- `confidence` = 1.0 (Phase 0 default — no AI scoring yet)

---

## 7. Frontend

**Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS, `next/font` (Geist, Outfit, Geist Mono).

**Hearth/Meridian toggle:** CSS class on `<html>` (`data-mode="hearth"` / `data-mode="meridian"`), persisted to `localStorage`. Tailwind variant `meridian:` for density overrides.

**The Orb:** Rendered on all authenticated pages. Phase 0: inert pulsing animation only. Wired to Custodian in Phase 3.

### Pages

| Route | Page | Notes |
|---|---|---|
| `/login` | Login | Password input, JWT cookie set on success |
| `/dashboard` | Dashboard | Source count, observation count, pending jobs, recent sources list |
| `/import` | Import | Drop zone + format grid, upload progress via polling |
| `/sources` | Sources list | Filterable table, status badges, observation count |
| `/observations` | Observation browser | Filterable card list, Hearth mode default |

### API client

`frontend/src/lib/api.ts` — typed fetch wrapper, calls relative `/api/*` paths, includes credentials (cookie). All responses typed against shared schema.

**Dev proxy (mirrors prod):** `next.config.js` rewrites `/api/:path*` → `http://localhost:8000/:path*`. The browser only sees the frontend origin in both dev and prod, so the `HttpOnly; SameSite=Lax` cookie works without CORS. No `NEXT_PUBLIC_API_URL` needed — paths are always relative.

---

## 8. CI Pipeline

### `pr.yml` — on every pull request

```yaml
jobs:
  python:
    services:
      postgres: { image: pgvector/pgvector:pg16 }
      redis: { image: redis:7-alpine }
    steps:
      - ruff check kernel/ backend/ worker/
      - mypy kernel/ backend/ worker/
      - alembic upgrade head
      - alembic check          # no unapplied migrations
      - pytest --cov=kernel --cov=backend (80% minimum)

  typescript:
    steps:
      - eslint frontend/src/
      - tsc --noEmit
      - jest --coverage (80% minimum)

  docker:
    steps:
      - docker build ./backend
      - docker build ./worker
      - docker build ./frontend
```

### `main.yml` — on merge to `main`

All PR jobs, then:

```yaml
  push:
    steps:
      - docker build + push to ghcr.io/pxm-0/locigraph-backend:${SHA}
      - docker build + push to ghcr.io/pxm-0/locigraph-worker:${SHA}
      - docker build + push to ghcr.io/pxm-0/locigraph-frontend:${SHA}

  deploy: (optional, manual trigger)
    steps:
      - SSH to homelab
      - docker compose pull
      - docker compose up -d
```

---

## 9. Environment Variables

```bash
# .env.example

# Database
POSTGRES_PASSWORD=changeme        # owner role 'locigraph' — migrations only
APP_DB_PASSWORD=changeme           # non-owner role 'locigraph_app' — app + workers (RLS enforced)

# Auth
JWT_SECRET=changeme-generate-with-openssl-rand-hex-32
LOCIGRAPH_EMAIL=you@example.com
LOCIGRAPH_PASSWORD=changeme

# AI (Phase 1+)
ACTIVE_AI_PROVIDER=openai
OPENAI_API_KEY=

# Storage (Phase 0: local volume. Phase 1+: swap for S3)
RAW_STORAGE_PATH=/data/raw

# Retention
RAW_RETENTION_DAYS=7

# Redis
REDIS_URL=redis://redis:6379
```

---

## 10. Learning Guide

Phase 0 introduces several patterns that are worth understanding deeply before extending them.

### Row Level Security (RLS)

PostgreSQL RLS enforces that every query is automatically scoped to the current user — even if application code forgets a `WHERE user_id = ?` clause. The database rejects cross-tenant access before data leaves storage.

**How it works:**
1. The transaction sets `SET LOCAL app.current_user_id = '{user_id}'` as its first statement
2. The RLS policy `USING (...)` / `WITH CHECK (...)` is evaluated on every row touched
3. Rows that don't match are invisible — they don't appear in SELECT, can't be UPDATEd or DELETEd, and can't be INSERTed with a foreign `user_id`

**Footgun #1 — the owner bypass.** RLS is **not** enforced against a table's owner unless you `FORCE ROW LEVEL SECURITY`. If the app connected as the role that owns the tables, RLS would silently do nothing and every user could read everyone's data. We avoid this two ways: the app connects as a dedicated **non-owner** role (`locigraph_app`), and we `FORCE` RLS on every table as a backstop. The owner role (`locigraph`) is used only for migrations.

**Footgun #2 — `SET LOCAL` and connection pooling.** `SET LOCAL` is scoped to a transaction and reset on COMMIT/ROLLBACK. This matters because:
- Outside a transaction it is a no-op → the next query has no context and (failing closed) is rejected.
- A plain session-level `SET` would persist on a pooled connection after the request ends → the next request reusing that connection inherits the **previous user's** context → silent cross-tenant leak.

So the contract is absolute: **every scoped query runs inside a transaction whose first statement is `SET LOCAL app.current_user_id`.** The `db.session(user_id)` context manager is the only way to get a connection, and it always opens a transaction. There is no code path that queries without a user_id.

**Footgun #3 — failing open.** `current_setting('app.current_user_id')` is called without the `missing_ok` argument so it raises when unset. "No context" must mean "no data / error", never "all data".

**Defense in depth:** Application code also passes `user_id` explicitly to every repository function. The database (RLS) and the application (explicit arg) are two independent checks; both must fail for a leak.

**Testing:** Every integration test connects as `locigraph_app` (not the owner) and includes a cross-tenant test: create data as user A, set context to user B, assert empty result. Tests that run as the owner would pass even with broken RLS — so they must not.

### Sync API, Async Kernel, Sync Workers

The kernel is **async** (SQLAlchemy 2.0 + asyncpg). FastAPI consumes it natively. Dramatiq actors are **sync**, so each task drives the async kernel with `asyncio.run(...)` — a fresh event loop per task execution. Keep all DB logic in the async kernel; the `@dramatiq.actor` function stays a thin sync wrapper. This keeps one consistent async data layer shared by transport and workers, at the cost of one `asyncio.run` bridge in the worker.

### Dramatiq Workers

Dramatiq is a background task library backed by Redis. A task is a Python function decorated with `@dramatiq.actor`. When enqueued, the task payload is serialized to Redis. The worker process polls Redis and executes tasks.

**Key concepts:**
- `max_retries=3`: on exception, Dramatiq retries up to 3 times with exponential backoff
- `queue_name="ingestion"`: tasks are grouped into named queues; workers can be dedicated per queue
- **Idempotency:** tasks should be safe to run twice. `ingest_source` checks if observations already exist before inserting.

**Why not Celery?** Dramatiq has a simpler API, better error handling defaults, and no legacy baggage. The operational model (Redis broker, worker process) is identical.

### Parser Protocol

The `Parser` protocol defines a single method: `parse(path: Path) → list[Fragment]`. Every format parser implements this interface. The worker calls `get_parser(source_type)` which returns the correct implementation.

**Why a protocol over a base class?** Python structural typing — a class is a `Parser` if it has the right method, not because it inherits from anything. Easier to test (no inheritance hierarchy to set up) and easier to add new formats (just implement the method).

### JWT + httpOnly Cookies

JWTs are signed tokens that encode claims (user ID, expiry). The server validates the signature on every request — no database lookup required. `httpOnly` cookies are inaccessible to JavaScript, which prevents XSS attacks from stealing the token.

**Token lifetime:** 7 days. After expiry, the user must log in again. Token refresh is deferred to a later phase.

### Next.js App Router

Pages live in `frontend/src/app/`. Folders become URL segments. `page.tsx` renders the route. `layout.tsx` wraps children — used for the authenticated shell (sidebar, Orb).

**Server vs Client components:** By default, components are server-rendered. Add `"use client"` only when you need browser APIs (localStorage for mode toggle, event handlers for the Orb). Keep data fetching in Server Components where possible.

---

## 11. Out of Scope (Phase 0)

- AI extraction (claims, concepts) — Phase 1
- Graph building — Phase 1
- Embeddings / semantic search — Phase 1
- Contradiction detection — Phase 2
- Custodian (live Orb) — Phase 3
- Planetarium — Phase 4
- Source quarantine / purge job — Phase 1 cleanup task
- OAuth / multi-user registration — post-Phase 0
- S3 storage adapter — triggered by AWS migration
- WebSocket status updates — polling sufficient for Phase 0
