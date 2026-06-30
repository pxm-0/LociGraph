# LociGraph

A concept-centric memory architecture. LociGraph transforms raw personal data into
concepts, evidence-bound assertions, interpretive models, contradictions, and revisions —
navigable as a planetarium.

> LociGraph is not a web application with AI features.
> It is a knowledge engine that happens to expose a web interface.

---

## Architecture

```
Frontend (Next.js — Plan 4)
    │
    ▼
Caddy  (:80)  →  /api/*  →  Backend (FastAPI :8000)
          │
          └────  /*      →  Frontend (Next.js :3000)
                                │
                                ▼
                         Knowledge Kernel
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              PostgreSQL 16            Redis 7
              (+ pgvector)         (job queue)
                    │
                    ▼
              Worker (Dramatiq)
```

**Services**

| Service  | Image / Source       | Role |
|----------|----------------------|------|
| postgres | pgvector/pgvector:pg16 | Canonical storage + vector search |
| redis    | redis:7-alpine       | Dramatiq job queue |
| backend  | ./backend/Dockerfile | FastAPI API (uvicorn :8000) |
| worker   | ./worker/Dockerfile  | Dramatiq background workers |
| frontend | ./frontend/Dockerfile | Next.js archive interface |
| caddy    | caddy:2-alpine       | Reverse proxy — routes `/api/*` to backend and app routes to frontend |

---

## Quickstart — Docker (recommended)

### 1. Copy and configure environment

```bash
cp .env.example .env
# Edit .env — set real values for JWT_SECRET, LOCIGRAPH_EMAIL, LOCIGRAPH_PASSWORD
# For local dev the changeme defaults work out of the box
```

### 2. Start all services

```bash
docker compose up -d
```

### 3. Provision the admin user

```bash
docker compose exec backend python -m backend.app.scripts.init_user
```

### 4. Verify

```bash
curl http://localhost/api/auth/me    # → 401 (gateway live, auth required)
curl http://localhost/               # → LociGraph frontend
```

---

## Quickstart — Local Dev (Python venv)

Requires: Python 3.12, PostgreSQL 16 (+ pgvector), Redis 7.

```bash
# Start data layer (postgres + redis only)
docker compose up -d postgres redis

# Create and activate virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e ".[dev]"

# Set env vars (example)
export DATABASE_URL="postgresql+asyncpg://locigraph_app:changeme@localhost/locigraph"
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost/locigraph"
export REDIS_URL="redis://localhost:6379"
export JWT_SECRET="dev-secret"
export LOCIGRAPH_EMAIL="you@example.com"
export LOCIGRAPH_PASSWORD="changeme"
export RAW_STORAGE_PATH="/tmp/locigraph-raw"
export COOKIE_SECURE="false"

# Run migrations
alembic upgrade head

# Provision admin user
python -m backend.app.scripts.init_user

# Start API
uvicorn backend.app.main:app --reload

# Start worker (separate terminal)
dramatiq worker.main --processes 1 --threads 2
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in real values for production.

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Owner role password (`locigraph`) — migrations only |
| `APP_DB_PASSWORD` | yes | App role password (`locigraph_app`) — backend + worker |
| `JWT_SECRET` | yes | Token signing key — generate with `openssl rand -hex 32` |
| `LOCIGRAPH_EMAIL` | yes | Admin user email |
| `LOCIGRAPH_PASSWORD` | yes | Admin user password |
| `REDIS_URL` | yes | Redis connection URL (default: `redis://redis:6379`) |
| `RAW_STORAGE_PATH` | yes | Path for uploaded raw files (Docker default: `/data/raw`) |
| `ACTIVE_AI_PROVIDER` | no | AI provider: `openai` \| `anthropic` (default: `openai`) |
| `OPENAI_API_KEY` | no | OpenAI API key (required if provider is openai) |
| `COOKIE_SECURE` | no | Set `true` in production (HTTPS only cookies) |

---

## Frontend Dev

```bash
cd frontend
npm install
npm run dev
```

The frontend calls relative `/api/*` paths. In local Next dev, `next.config.mjs`
rewrites those requests to `http://localhost:8000`; in Docker, Caddy handles
the same route split at the single public origin.

---

## Running Tests

```bash
# Requires postgres + redis to be running (docker compose up -d postgres redis)
pytest
```

---

## Project Layout

```
locigraph/
├── kernel/          # Knowledge Kernel — framework-independent business logic
├── backend/
│   ├── app/         # FastAPI application
│   └── Dockerfile
├── frontend/        # Next.js application
├── worker/
│   ├── main.py      # Dramatiq worker entry point
│   └── Dockerfile
├── migrations/      # Alembic migrations
├── tests/
├── docker-compose.yml
├── Caddyfile
└── pyproject.toml
```

---

## Caddy Routing

`Caddyfile` configures Caddy as the single ingress at `:80`:

- `GET /api/*` → strips `/api` prefix → proxied to `backend:8000`
- All other paths → proxied to `frontend:3000`

---

## Volumes

| Volume | Mounted at | Purpose |
|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | Persistent database |
| `redis_data` | `/data` | Redis AOF / RDB persistence |
| `raw_data` | `/data/raw` (backend + worker) | Uploaded source files (shared) |
