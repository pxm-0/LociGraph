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
| caddy    | caddy:2-alpine       | Reverse proxy — routes `/api/*` to backend |

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
curl http://localhost/               # → "LociGraph API gateway"
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
export ACTIVE_AI_PROVIDER="openai"
export OPENAI_API_KEY=""
export OPENAI_EXTRACTION_MODEL="gpt-4o-mini"
export CLAIM_EXTRACTION_AUTORUN="false"
export CLAIM_EXTRACTION_BATCH_SIZE="12"
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
| `ACTIVE_AI_PROVIDER` | no | AI provider for Phase 1 extraction (default: `openai`) |
| `OPENAI_API_KEY` | no | OpenAI API key (required if provider is openai) |
| `OPENAI_EXTRACTION_MODEL` | no | OpenAI model used by claim extraction (default: `gpt-4o-mini`) |
| `CLAIM_EXTRACTION_AUTORUN` | no | Enqueue claim extraction after successful ingestion (`false` by default) |
| `CLAIM_EXTRACTION_BATCH_SIZE` | no | Observations per extraction request (default: `12`) |
| `COOKIE_SECURE` | no | Set `true` in production (HTTPS only cookies) |

---

## Running Tests

```bash
# Requires postgres + redis to be running (docker compose up -d postgres redis)
pytest
```

For local host tests that exercise uploads, set `RAW_STORAGE_PATH` to a writable
host path such as `/tmp/locigraph-raw`.

---

## Phase 1 Claim Extraction

Verified sources can produce proposed claims through:

- automatic `extract_claims` jobs after ingestion when `CLAIM_EXTRACTION_AUTORUN=true`
- manual `POST /api/sources/{source_id}/extract-claims`

Claim and concept-candidate rows are tenant-scoped by PostgreSQL RLS. Concept
candidates are proposed memory only; canonical concepts, graph edges,
contradiction detection, Custodian, and Planetarium work remain out of scope
for Phase 1 Plan 1 (embeddings are covered in Phase 1 Plan 3).

---

## Phase 1 Concept Promotion

Proposed concept candidates are reviewed on `/claims`:

- **Approve** (`POST /api/concept-candidates/{id}/approve`) dedups against
  existing concepts case-insensitively within the same `concept_type`,
  reusing a match or creating a new canonical concept, then links a
  `claim_concept_edges` graph edge from the originating claim to the
  concept. Re-approving an already-accepted candidate is a safe no-op — it
  returns the existing concept/edge rather than erroring or duplicating.
- **Reject** (`POST /api/concept-candidates/{id}/reject`) just marks the
  candidate rejected; no concept or edge is created.

Canonical concepts are browsable at `/concepts` (`GET /api/concepts`,
`GET /api/concepts/{id}`, `GET /api/concepts/{id}/claims`), scoped by RLS
like every other table. Concept-to-concept relationships, inferred graph
edges, and an interactive graph visualization are out of scope for this
plan — see the Planetarium (Phase 4).

---

## Phase 1 Embeddings & Semantic Search

Claims are embedded via OpenAI (`text-embedding-3-small` by default) into a
pgvector-backed `semantic_vectors` table (HNSW cosine index), one row per
claim:

- automatic `embed_claims` jobs after each extraction chunk persists claims,
  when `EMBEDDING_AUTORUN=true`
- manual `POST /api/sources/{source_id}/embed-claims`

`GET /api/search?q=...&limit=20` embeds the query and ranks claims by cosine
similarity, scoped by RLS like every other query. Concept embeddings, hybrid
keyword+semantic search, and re-ranking are out of scope for this plan — see
the Planetarium (Phase 4), which consumes these embeddings for its spatial
projection layer.

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

## Project Layout

```
locigraph/
├── kernel/          # Knowledge Kernel — framework-independent business logic
├── backend/
│   ├── app/         # FastAPI application
│   └── Dockerfile
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
- All other paths → `"LociGraph API gateway"` (frontend added in Plan 4)

---

## Volumes

| Volume | Mounted at | Purpose |
|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | Persistent database |
| `redis_data` | `/data` | Redis AOF / RDB persistence |
| `raw_data` | `/data/raw` (backend + worker) | Uploaded source files (shared) |
