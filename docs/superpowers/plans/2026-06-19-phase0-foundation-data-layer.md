# Phase 0 — Plan 1: Foundation & Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the LociGraph monorepo, Postgres+pgvector via Docker, an Alembic migration that creates the schema with two-role Row-Level Security, and an async kernel data layer (session context manager + repositories) whose tenant isolation is proven by a cross-tenant integration test.

**Architecture:** A Python monorepo with a framework-independent async `kernel` package (SQLAlchemy 2.0 Core + asyncpg). All tenant data is isolated by PostgreSQL RLS. The application connects as a **non-owner** role (`locigraph_app`) so RLS is enforced; migrations run as the **owner** (`locigraph`). Every query runs inside a transaction whose first statement sets `app.current_user_id` via `set_config(..., true)`; the `kernel.db.session(user_id)` context manager is the only way to obtain a connection.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (Core, async), asyncpg, Alembic, PostgreSQL 16 + pgvector, Docker Compose, Caddy, pytest + pytest-asyncio, ruff, mypy.

## Global Constraints

- Python version floor: **3.12**.
- DB driver: **asyncpg** via SQLAlchemy async engine (`postgresql+asyncpg://`).
- The application and workers connect ONLY as the non-owner role **`locigraph_app`**. The owner role **`locigraph`** is used ONLY for migrations.
- Every data table has `user_id UUID NOT NULL REFERENCES users(id)`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, and a policy with both `USING` and `WITH CHECK`.
- Tenant context is set with `SELECT set_config('app.current_user_id', :uid, true)` (transaction-local, parameterized — never string-interpolated).
- `current_setting('app.current_user_id')` is read WITHOUT `missing_ok` so it fails closed.
- Test coverage minimum: **80%** for the `kernel` package.
- Immutable style: repositories return new domain objects; no in-place mutation of shared state.
- Naming: `snake_case` Python, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- No hardcoded secrets — all passwords/keys come from environment variables.

---

## File Structure

```
locigraph/
├── pyproject.toml                      # Task 1 — tooling + deps for kernel/backend/worker
├── .gitignore                          # Task 1
├── docker-compose.yml                  # Task 2
├── Caddyfile                           # Task 2
├── .env.example                        # Task 2
├── alembic.ini                         # Task 3
├── migrations/
│   ├── env.py                          # Task 3
│   ├── script.py.mako                  # Task 3
│   └── versions/
│       └── 0001_initial_schema.py      # Task 3
├── kernel/
│   ├── __init__.py                     # Task 1
│   ├── models.py                       # Task 4 — domain dataclasses
│   └── db/
│       ├── __init__.py                 # Task 5
│       ├── engine.py                   # Task 5 — async engine factory
│       ├── session.py                  # Task 5 — RLS session context manager
│       ├── base_repository.py          # Task 6 — shared repository helpers
│       ├── sources.py                  # Task 6 — SourceRepository
│       ├── fragments.py                # Task 7 — FragmentRepository
│       ├── observations.py             # Task 7 — ObservationRepository
│       └── jobs.py                     # Task 8 — JobRepository
└── tests/
    ├── conftest.py                     # Task 5 — async fixtures, app-role engine
    └── kernel/
        ├── test_session.py             # Task 5 — RLS smoke test
        ├── test_sources_repository.py  # Task 6
        ├── test_fragments_observations_repository.py  # Task 7
        ├── test_jobs_repository.py     # Task 8
        └── test_tenant_isolation.py    # Task 9 — cross-tenant security gate
```

---

### Task 1: Project scaffolding & Python tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `kernel/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: an installable workspace where `ruff`, `mypy`, and `pytest` run. Package import root `kernel`.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_kernel_imports():
    import kernel

    assert kernel is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel'`

- [ ] **Step 3: Create the package and tooling config**

`kernel/__init__.py`:
```python
"""LociGraph Knowledge Kernel — framework-independent core."""

__version__ = "0.0.0"
```

`pyproject.toml`:
```toml
[project]
name = "locigraph"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
    "sqlalchemy[asyncio]>=2.0,<2.1",
    "asyncpg>=0.29,<0.30",
    "alembic>=1.13,<1.14",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-asyncio>=0.23,<0.24",
    "pytest-cov>=5.0,<6.0",
    "ruff>=0.5,<0.6",
    "mypy>=1.10,<1.11",
]

[tool.setuptools.packages.find]
include = ["kernel*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--cov=kernel --cov-report=term-missing"
testpaths = ["tests"]
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
node_modules/
.next/
data/
caddy_data/
postgres_data/
```

- [ ] **Step 4: Install and run the test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Verify lint and types are clean**

Run: `ruff check . && mypy kernel`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore kernel/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold python workspace and tooling"
```

---

### Task 2: Docker Compose, Caddy, environment

**Files:**
- Create: `docker-compose.yml`
- Create: `Caddyfile`
- Create: `.env.example`
- Test: manual `docker compose config` validation (no unit test — infra)

**Interfaces:**
- Consumes: nothing from prior tasks
- Produces: a `postgres` service (pgvector/pg16) reachable at `localhost:5432` with DB `locigraph`, owner role `locigraph`; a `redis` service at `localhost:6379`. These back the test database used from Task 5 onward.

- [ ] **Step 1: Create `.env.example`**

```bash
# Database
POSTGRES_PASSWORD=changeme            # owner role 'locigraph' — migrations only
APP_DB_PASSWORD=changeme              # non-owner role 'locigraph_app' — app + workers

# Auth (used in Plan 3)
JWT_SECRET=changeme-generate-with-openssl-rand-hex-32
LOCIGRAPH_EMAIL=you@example.com
LOCIGRAPH_PASSWORD=changeme

# AI (Plan/Phase 1+)
ACTIVE_AI_PROVIDER=openai
OPENAI_API_KEY=

# Storage
RAW_STORAGE_PATH=/data/raw
RAW_RETENTION_DAYS=7

# Redis
REDIS_URL=redis://redis:6379
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: locigraph
      POSTGRES_USER: locigraph
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U locigraph"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

> Note: `backend`, `worker`, `frontend`, and `caddy` services are added in Plans 3–4. Phase 1 of this plan only needs Postgres + Redis running for tests.

- [ ] **Step 3: Create a minimal `Caddyfile` placeholder**

`Caddyfile`:
```
# Production reverse proxy. Frontend + API served from one origin.
# Fleshed out in Plan 4 once backend/frontend services exist.
:80 {
	respond "LociGraph — services not yet wired" 503
}
```

- [ ] **Step 4: Validate compose config**

Run: `cp .env.example .env && docker compose config`
Expected: prints resolved config, no errors

- [ ] **Step 5: Bring up data services and verify**

Run: `docker compose up -d postgres redis && docker compose ps`
Expected: both services `running`/`healthy`. Verify Postgres: `docker compose exec postgres pg_isready -U locigraph` → `accepting connections`

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml Caddyfile .env.example
git commit -m "chore: add postgres+redis docker compose and env template"
```

---

### Task 3: Alembic setup & initial schema migration (tables, roles, RLS, pgvector)

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_initial_schema.py`
- Test: `tests/kernel/test_migration.py`

**Interfaces:**
- Consumes: `MIGRATION_DATABASE_URL` (owner) and `APP_DB_PASSWORD` env vars.
- Produces: schema with tables `users, sources, fragments, observations, jobs, audit_logs`; role `locigraph_app` (non-owner, DML granted); `ENABLE`+`FORCE` RLS and `USING`/`WITH CHECK` policies on `sources, fragments, observations, jobs`; `vector` extension. Revision id `0001`.

- [ ] **Step 1: Write the failing test**

`tests/kernel/test_migration.py`:
```python
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OWNER_URL = os.environ["MIGRATION_DATABASE_URL"]


@pytest.mark.asyncio
async def test_rls_is_forced_on_data_tables():
    engine = create_async_engine(OWNER_URL)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "WHERE relrowsecurity AND relforcerowsecurity "
                    "ORDER BY relname"
                )
            )
            forced = {r[0] for r in rows}
        assert {"sources", "fragments", "observations", "jobs"} <= forced
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_app_role_exists_and_is_not_superuser():
    engine = create_async_engine(OWNER_URL)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = 'locigraph_app'"
                    )
                )
            ).first()
        assert row is not None, "locigraph_app role must exist"
        assert row[0] is False, "app role must not be superuser"
        assert row[1] is False, "app role must not bypass RLS"
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph" pytest tests/kernel/test_migration.py -v`
Expected: FAIL (tables/role do not exist yet → assertions fail or empty results)

- [ ] **Step 3: Create Alembic config and env**

`alembic.ini` (only the keys that matter; URL is injected in `env.py`):
```ini
[alembic]
script_location = migrations
prepend_sys_path = .

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`migrations/env.py`:
```python
import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Migrations run as the OWNER role.
DATABASE_URL = os.environ["MIGRATION_DATABASE_URL"]


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


run_migrations_online()
```

`migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Write the initial migration**

`migrations/versions/0001_initial_schema.py`:
```python
"""initial schema with two-role RLS

Revision ID: 0001
Revises:
Create Date: 2026-06-19
"""
import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DATA_TABLES = ["sources", "fragments", "observations", "jobs"]


def upgrade() -> None:
    app_password = os.environ["APP_DB_PASSWORD"]

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
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
            UNIQUE (user_id, checksum_sha256)
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )

    # Non-owner application role.
    op.execute(
        f"CREATE ROLE locigraph_app LOGIN PASSWORD '{app_password}'"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "sources, fragments, observations, jobs TO locigraph_app"
    )
    op.execute("GRANT SELECT, INSERT ON audit_logs TO locigraph_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON users TO locigraph_app")
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO locigraph_app"
    )

    # Enable + FORCE RLS and add USING/WITH CHECK policies.
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    for table in ["audit_logs", "jobs", "observations", "fragments", "sources", "users"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP ROLE IF EXISTS locigraph_app")
```

> **Why `set_config(..., true)` is used at query time (Task 5), not string interpolation:** the policy reads `current_setting('app.current_user_id')`; the *value* is set per-transaction with a bound parameter so a user_id can never be injected. The migration string-interpolates only the app password, which comes from a trusted env var, not user input.

- [ ] **Step 5: Apply the migration**

Run:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
export APP_DB_PASSWORD="changeme"
alembic upgrade head
```
Expected: `Running upgrade -> 0001, initial schema with two-role RLS`

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/kernel/test_migration.py -v`
Expected: PASS (both tests)

- [ ] **Step 7: Verify downgrade/upgrade round-trips**

Run: `alembic downgrade base && alembic upgrade head`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add alembic.ini migrations/ tests/kernel/test_migration.py
git commit -m "feat: initial schema with two-role forced RLS"
```

---

### Task 4: Kernel domain models

**Files:**
- Create: `kernel/models.py`
- Test: `tests/kernel/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: frozen dataclasses `User, Source, Fragment, Observation, Job` with `from_row(mapping)` classmethods. These are the return types of every repository.

- [ ] **Step 1: Write the failing test**

`tests/kernel/test_models.py`:
```python
import uuid
from datetime import datetime, timezone

from kernel.models import Observation, Source


def test_source_from_row_maps_fields():
    row = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "source_type": "markdown",
        "original_filename": "notes.md",
        "checksum_sha256": "abc",
        "import_status": "PENDING",
    }
    source = Source.from_row(row)
    assert source.source_type == "markdown"
    assert source.import_status == "PENDING"
    assert source.original_filename == "notes.md"


def test_observation_is_immutable():
    obs = Observation.from_row(
        {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "content": "hello",
            "confidence": 1.0,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
    )
    try:
        obs.content = "changed"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "frozen dataclass must reject mutation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/kernel/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` for `kernel.models`

- [ ] **Step 3: Implement the models**

`kernel/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "User":
        return cls(id=row["id"], email=row["email"], created_at=row.get("created_at"))


@dataclass(frozen=True, slots=True)
class Source:
    id: UUID
    user_id: UUID
    source_type: str
    checksum_sha256: str
    import_status: str
    original_filename: str | None = None
    original_mime_type: str | None = None
    file_size_bytes: int | None = None
    raw_storage_path: str | None = None
    verified_at: datetime | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Source":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_type=row["source_type"],
            checksum_sha256=row["checksum_sha256"],
            import_status=row["import_status"],
            original_filename=row.get("original_filename"),
            original_mime_type=row.get("original_mime_type"),
            file_size_bytes=row.get("file_size_bytes"),
            raw_storage_path=row.get("raw_storage_path"),
            verified_at=row.get("verified_at"),
            metadata=row.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class Fragment:
    id: UUID
    user_id: UUID
    source_id: UUID
    raw_index: int | None = None
    extracted_text: str | None = None
    timestamp: datetime | None = None
    author: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Fragment":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            raw_index=row.get("raw_index"),
            extracted_text=row.get("extracted_text"),
            timestamp=row.get("timestamp"),
            author=row.get("author"),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    id: UUID
    user_id: UUID
    content: str
    confidence: float
    status: str
    created_at: datetime
    source_id: UUID | None = None
    fragment_id: UUID | None = None
    observed_at: datetime | None = None
    speaker: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Observation":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            confidence=float(row["confidence"]),
            status=row["status"],
            created_at=row["created_at"],
            source_id=row.get("source_id"),
            fragment_id=row.get("fragment_id"),
            observed_at=row.get("observed_at"),
            speaker=row.get("speaker"),
        )


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    user_id: UUID
    job_type: str
    status: str
    attempts: int = 0
    error: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Job":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            job_type=row["job_type"],
            status=row["status"],
            attempts=row.get("attempts", 0),
            error=row.get("error"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/kernel/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Verify lint and types**

Run: `ruff check kernel && mypy kernel`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add kernel/models.py tests/kernel/test_models.py
git commit -m "feat: immutable kernel domain models"
```

---

### Task 5: Async engine + RLS session context manager

**Files:**
- Create: `kernel/db/__init__.py`
- Create: `kernel/db/engine.py`
- Create: `kernel/db/session.py`
- Create: `tests/conftest.py`
- Test: `tests/kernel/test_session.py`

**Interfaces:**
- Consumes: `DATABASE_URL` (app role) env var; the schema from Task 3.
- Produces:
  - `kernel.db.engine.get_engine() -> AsyncEngine` (singleton, app role).
  - `kernel.db.session.session(user_id: str | UUID) -> AsyncIterator[AsyncConnection]` — async context manager that opens a transaction and runs `SELECT set_config('app.current_user_id', :uid, true)` first. This is the ONLY sanctioned way to get a DB connection in the kernel.

- [ ] **Step 1: Write the conftest fixtures**

`tests/conftest.py`:
```python
import os
import uuid

import pytest_asyncio
from sqlalchemy import text

from kernel.db.engine import get_engine
from kernel.db.session import session


@pytest_asyncio.fixture
async def make_user():
    """Insert a user row (as owner-less app role won't pass RLS for users table —
    users has no RLS, app role has INSERT). Returns the new user's id."""
    created: list[uuid.UUID] = []

    async def _make(email: str | None = None) -> uuid.UUID:
        uid = uuid.uuid4()
        email = email or f"{uid}@example.com"
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) "
                    "VALUES (:id, :email, 'x')"
                ),
                {"id": uid, "email": email},
            )
        created.append(uid)
        return uid

    yield _make

    engine = get_engine()
    async with engine.begin() as conn:
        for uid in created:
            await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})


@pytest_asyncio.fixture(autouse=True)
def require_app_database_url():
    assert "DATABASE_URL" in os.environ, "DATABASE_URL (app role) must be set for tests"
```

- [ ] **Step 2: Write the failing test**

`tests/kernel/test_session.py`:
```python
import uuid

import pytest
from sqlalchemy import text

from kernel.db.session import session


@pytest.mark.asyncio
async def test_session_sets_tenant_context(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        value = (
            await conn.execute(text("SELECT current_setting('app.current_user_id')"))
        ).scalar_one()
    assert value == str(user_id)


@pytest.mark.asyncio
async def test_context_does_not_leak_across_sessions(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await conn.execute(text("SELECT 1"))
    # New session WITHOUT a user must fail closed when reading data tables.
    from kernel.db.engine import get_engine

    engine = get_engine()
    async with engine.connect() as conn:
        with pytest.raises(Exception):
            # No set_config → current_setting errors → fail closed.
            await conn.execute(text("SELECT count(*) FROM sources"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/kernel/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError` for `kernel.db.session`

- [ ] **Step 4: Implement engine and session**

`kernel/db/__init__.py`:
```python
"""Kernel data-access layer."""
```

`kernel/db/engine.py`:
```python
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, connecting as the app (non-owner) role."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"]
        _engine = create_async_engine(url, pool_pre_ping=True)
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
```

`kernel/db/session.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.engine import get_engine


@asynccontextmanager
async def session(user_id: str | UUID) -> AsyncIterator[AsyncConnection]:
    """Open a transaction scoped to `user_id` via transaction-local set_config.

    This is the ONLY sanctioned way to obtain a kernel DB connection. Every query
    inside the block runs under RLS for `user_id`. The setting is reset on exit.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(user_id)},
            )
            yield conn
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
export DATABASE_URL="postgresql+asyncpg://locigraph_app:changeme@localhost:5432/locigraph"
pytest tests/kernel/test_session.py -v
```
Expected: PASS (both tests)

- [ ] **Step 6: Verify lint and types**

Run: `ruff check kernel && mypy kernel`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add kernel/db/__init__.py kernel/db/engine.py kernel/db/session.py \
        tests/conftest.py tests/kernel/test_session.py
git commit -m "feat: rls-scoped async session context manager"
```

---

### Task 6: Repository base + SourceRepository

**Files:**
- Create: `kernel/db/base_repository.py`
- Create: `kernel/db/sources.py`
- Test: `tests/kernel/test_sources_repository.py`

**Interfaces:**
- Consumes: `kernel.db.session.session`, `kernel.models.Source`, an `AsyncConnection`.
- Produces:
  - `BaseRepository(conn: AsyncConnection)` storing `self.conn`.
  - `SourceRepository.create(user_id, source_type, checksum_sha256, *, original_filename=None, original_mime_type=None, file_size_bytes=None, raw_storage_path=None) -> Source`
  - `SourceRepository.get(source_id) -> Source | None`
  - `SourceRepository.set_status(source_id, status) -> None`
  - `SourceRepository.mark_verified(source_id) -> None`
  - `SourceRepository.list(limit=50, offset=0) -> list[Source]`

- [ ] **Step 1: Write the failing test**

`tests/kernel/test_sources_repository.py`:
```python
import uuid

import pytest

from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_create_and_get_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        created = await repo.create(
            user_id, "markdown", "checksum-1", original_filename="a.md"
        )
        fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.source_type == "markdown"
    assert fetched.import_status == "PENDING"
    assert fetched.original_filename == "a.md"


@pytest.mark.asyncio
async def test_status_transitions(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        src = await repo.create(user_id, "pdf", "checksum-2")
        await repo.set_status(src.id, "INGESTING")
        await repo.mark_verified(src.id)
        fetched = await repo.get(src.id)
    assert fetched is not None
    assert fetched.import_status == "VERIFIED"
    assert fetched.verified_at is not None


@pytest.mark.asyncio
async def test_duplicate_checksum_rejected(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = SourceRepository(conn)
        await repo.create(user_id, "json", "dupe")
        with pytest.raises(Exception):
            await repo.create(user_id, "json", "dupe")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/kernel/test_sources_repository.py -v`
Expected: FAIL with `ModuleNotFoundError` for `kernel.db.sources`

- [ ] **Step 3: Implement base repository and SourceRepository**

`kernel/db/base_repository.py`:
```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection


class BaseRepository:
    """Holds the RLS-scoped connection. Subclasses issue queries against it."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
```

`kernel/db/sources.py`:
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from kernel.db.base_repository import BaseRepository
from kernel.models import Source

_COLUMNS = (
    "id, user_id, source_type, original_filename, original_mime_type, "
    "checksum_sha256, file_size_bytes, raw_storage_path, import_status, verified_at, metadata"
)


class SourceRepository(BaseRepository):
    async def create(
        self,
        user_id: str | UUID,
        source_type: str,
        checksum_sha256: str,
        *,
        original_filename: str | None = None,
        original_mime_type: str | None = None,
        file_size_bytes: int | None = None,
        raw_storage_path: str | None = None,
    ) -> Source:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO sources
                        (user_id, source_type, checksum_sha256, original_filename,
                         original_mime_type, file_size_bytes, raw_storage_path)
                    VALUES
                        (:user_id, :source_type, :checksum, :filename,
                         :mime, :size, :path)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_type": source_type,
                    "checksum": checksum_sha256,
                    "filename": original_filename,
                    "mime": original_mime_type,
                    "size": file_size_bytes,
                    "path": raw_storage_path,
                },
            )
        ).mappings().one()
        return Source.from_row(row)

    async def get(self, source_id: str | UUID) -> Source | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM sources WHERE id = :id"),
                {"id": str(source_id)},
            )
        ).mappings().first()
        return Source.from_row(row) if row else None

    async def set_status(self, source_id: str | UUID, status: str) -> None:
        await self.conn.execute(
            text("UPDATE sources SET import_status = :status WHERE id = :id"),
            {"status": status, "id": str(source_id)},
        )

    async def mark_verified(self, source_id: str | UUID) -> None:
        await self.conn.execute(
            text(
                "UPDATE sources SET import_status = 'VERIFIED', verified_at = now() "
                "WHERE id = :id"
            ),
            {"id": str(source_id)},
        )

    async def list(self, limit: int = 50, offset: int = 0) -> list[Source]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM sources "
                    "ORDER BY imported_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Source.from_row(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/kernel/test_sources_repository.py -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Verify lint and types**

Run: `ruff check kernel && mypy kernel`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add kernel/db/base_repository.py kernel/db/sources.py \
        tests/kernel/test_sources_repository.py
git commit -m "feat: source repository with rls-scoped queries"
```

---

### Task 7: FragmentRepository & ObservationRepository

**Files:**
- Create: `kernel/db/fragments.py`
- Create: `kernel/db/observations.py`
- Test: `tests/kernel/test_fragments_observations_repository.py`

**Interfaces:**
- Consumes: `BaseRepository`, `kernel.models.Fragment`, `kernel.models.Observation`, `kernel.db.session.session`.
- Produces:
  - `FragmentRepository.bulk_insert(rows: list[dict], source_id, user_id) -> list[UUID]` where each dict has keys `raw_index, extracted_text, timestamp, author` (all optional except `extracted_text`).
  - `FragmentRepository.list_for_source(source_id) -> list[Fragment]`
  - `ObservationRepository.bulk_insert(rows: list[dict], source_id, user_id) -> list[UUID]` where each dict has keys `content` (required), `observed_at, speaker, fragment_id, context_before, context_after` (optional).
  - `ObservationRepository.list_for_source(source_id) -> list[Observation]`
  - `ObservationRepository.count_for_source(source_id) -> int`

- [ ] **Step 1: Write the failing test**

`tests/kernel/test_fragments_observations_repository.py`:
```python
import pytest

from kernel.db.fragments import FragmentRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_bulk_insert_fragments_and_observations(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "chatgpt", "c-frag-1")

        frag_ids = await FragmentRepository(conn).bulk_insert(
            [
                {"raw_index": 0, "extracted_text": "hi", "author": "me"},
                {"raw_index": 1, "extracted_text": "there", "author": "you"},
            ],
            src.id,
            user_id,
        )
        assert len(frag_ids) == 2

        obs_ids = await ObservationRepository(conn).bulk_insert(
            [
                {"content": "hi", "speaker": "me", "fragment_id": frag_ids[0]},
                {"content": "there", "speaker": "you", "fragment_id": frag_ids[1]},
            ],
            src.id,
            user_id,
        )
        assert len(obs_ids) == 2

        count = await ObservationRepository(conn).count_for_source(src.id)
        observations = await ObservationRepository(conn).list_for_source(src.id)
    assert count == 2
    assert {o.content for o in observations} == {"hi", "there"}


@pytest.mark.asyncio
async def test_bulk_insert_empty_returns_empty(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "json", "c-frag-2")
        result = await FragmentRepository(conn).bulk_insert([], src.id, user_id)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/kernel/test_fragments_observations_repository.py -v`
Expected: FAIL with `ModuleNotFoundError` for `kernel.db.fragments`

- [ ] **Step 3: Implement the repositories**

`kernel/db/fragments.py`:
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from kernel.db.base_repository import BaseRepository
from kernel.models import Fragment

_COLUMNS = "id, user_id, source_id, raw_index, extracted_text, timestamp, author"


class FragmentRepository(BaseRepository):
    async def bulk_insert(
        self, rows: list[dict], source_id: str | UUID, user_id: str | UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for row in rows:
            new_id = (
                await self.conn.execute(
                    text(
                        """
                        INSERT INTO fragments
                            (user_id, source_id, raw_index, extracted_text, timestamp, author)
                        VALUES (:user_id, :source_id, :raw_index, :text, :ts, :author)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "source_id": str(source_id),
                        "raw_index": row.get("raw_index"),
                        "text": row.get("extracted_text"),
                        "ts": row.get("timestamp"),
                        "author": row.get("author"),
                    },
                )
            ).scalar_one()
            ids.append(new_id)
        return ids

    async def list_for_source(self, source_id: str | UUID) -> list[Fragment]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM fragments "
                    "WHERE source_id = :sid ORDER BY raw_index"
                ),
                {"sid": str(source_id)},
            )
        ).mappings().all()
        return [Fragment.from_row(r) for r in rows]
```

`kernel/db/observations.py`:
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from kernel.db.base_repository import BaseRepository
from kernel.models import Observation

_COLUMNS = (
    "id, user_id, source_id, fragment_id, observed_at, speaker, "
    "content, confidence, status, created_at"
)


class ObservationRepository(BaseRepository):
    async def bulk_insert(
        self, rows: list[dict], source_id: str | UUID, user_id: str | UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for row in rows:
            new_id = (
                await self.conn.execute(
                    text(
                        """
                        INSERT INTO observations
                            (user_id, source_id, fragment_id, observed_at, speaker,
                             content, context_before, context_after)
                        VALUES (:user_id, :source_id, :fragment_id, :observed_at, :speaker,
                                :content, :ctx_before, :ctx_after)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "source_id": str(source_id),
                        "fragment_id": row.get("fragment_id"),
                        "observed_at": row.get("observed_at"),
                        "speaker": row.get("speaker"),
                        "content": row["content"],
                        "ctx_before": row.get("context_before"),
                        "ctx_after": row.get("context_after"),
                    },
                )
            ).scalar_one()
            ids.append(new_id)
        return ids

    async def list_for_source(self, source_id: str | UUID) -> list[Observation]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM observations "
                    "WHERE source_id = :sid ORDER BY created_at"
                ),
                {"sid": str(source_id)},
            )
        ).mappings().all()
        return [Observation.from_row(r) for r in rows]

    async def count_for_source(self, source_id: str | UUID) -> int:
        return (
            await self.conn.execute(
                text("SELECT count(*) FROM observations WHERE source_id = :sid"),
                {"sid": str(source_id)},
            )
        ).scalar_one()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/kernel/test_fragments_observations_repository.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Verify lint and types**

Run: `ruff check kernel && mypy kernel`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add kernel/db/fragments.py kernel/db/observations.py \
        tests/kernel/test_fragments_observations_repository.py
git commit -m "feat: fragment and observation repositories"
```

---

### Task 8: JobRepository

**Files:**
- Create: `kernel/db/jobs.py`
- Test: `tests/kernel/test_jobs_repository.py`

**Interfaces:**
- Consumes: `BaseRepository`, `kernel.models.Job`.
- Produces:
  - `JobRepository.create(user_id, job_type, *, payload=None) -> Job`
  - `JobRepository.mark_running(job_id) -> None`
  - `JobRepository.mark_completed(job_id, result=None) -> None`
  - `JobRepository.record_attempt(job_id, error) -> None` (increments `attempts`, sets `error`, status `failed`)
  - `JobRepository.get(job_id) -> Job | None`

- [ ] **Step 1: Write the failing test**

`tests/kernel/test_jobs_repository.py`:
```python
import pytest

from kernel.db.jobs import JobRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_job_lifecycle(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "ingest_source", payload={"source_id": "x"})
        assert job.status == "pending"

        await repo.mark_running(job.id)
        await repo.mark_completed(job.id, result={"observations": 5})
        done = await repo.get(job.id)
    assert done is not None
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_record_attempt_increments_and_fails(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "ingest_source")
        await repo.record_attempt(job.id, error="boom")
        failed = await repo.get(job.id)
    assert failed is not None
    assert failed.attempts == 1
    assert failed.status == "failed"
    assert failed.error == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/kernel/test_jobs_repository.py -v`
Expected: FAIL with `ModuleNotFoundError` for `kernel.db.jobs`

- [ ] **Step 3: Implement JobRepository**

`kernel/db/jobs.py`:
```python
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text

from kernel.db.base_repository import BaseRepository
from kernel.models import Job

_COLUMNS = "id, user_id, job_type, status, attempts, error"


class JobRepository(BaseRepository):
    async def create(
        self, user_id: str | UUID, job_type: str, *, payload: dict | None = None
    ) -> Job:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO jobs (user_id, job_type, payload)
                    VALUES (:user_id, :job_type, CAST(:payload AS JSONB))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "job_type": job_type,
                    "payload": json.dumps(payload or {}),
                },
            )
        ).mappings().one()
        return Job.from_row(row)

    async def mark_running(self, job_id: str | UUID) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET status = 'running', started_at = now() WHERE id = :id"
            ),
            {"id": str(job_id)},
        )

    async def mark_completed(
        self, job_id: str | UUID, result: dict | None = None
    ) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET status = 'completed', completed_at = now(), "
                "result = CAST(:result AS JSONB) WHERE id = :id"
            ),
            {"id": str(job_id), "result": json.dumps(result or {})},
        )

    async def record_attempt(self, job_id: str | UUID, error: str) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET attempts = attempts + 1, status = 'failed', "
                "error = :error WHERE id = :id"
            ),
            {"id": str(job_id), "error": error},
        )

    async def get(self, job_id: str | UUID) -> Job | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM jobs WHERE id = :id"),
                {"id": str(job_id)},
            )
        ).mappings().first()
        return Job.from_row(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/kernel/test_jobs_repository.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Verify lint and types**

Run: `ruff check kernel && mypy kernel`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add kernel/db/jobs.py tests/kernel/test_jobs_repository.py
git commit -m "feat: job ledger repository"
```

---

### Task 9: Cross-tenant isolation integration test (security gate)

**Files:**
- Test: `tests/kernel/test_tenant_isolation.py`

**Interfaces:**
- Consumes: `SourceRepository`, `ObservationRepository`, `session`, `make_user` fixture.
- Produces: the executable proof that RLS isolates tenants. No production code — this task may surface a bug in earlier tasks; if it does, fix the offending task.

- [ ] **Step 1: Write the cross-tenant test**

`tests/kernel/test_tenant_isolation.py`:
```python
import pytest

from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_user_b_cannot_read_user_a_sources(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src_a = await SourceRepository(conn).create(user_a, "markdown", "iso-a")

    # User B lists sources — must NOT see user A's row.
    async with session(user_b) as conn:
        b_sources = await SourceRepository(conn).list()
    assert all(s.id != src_a.id for s in b_sources)

    # User B fetches A's source by id — RLS hides it → None.
    async with session(user_b) as conn:
        leaked = await SourceRepository(conn).get(src_a.id)
    assert leaked is None


@pytest.mark.asyncio
async def test_user_b_cannot_insert_rows_owned_by_user_a(make_user):
    user_a = await make_user()
    user_b = await make_user()

    # User B opens a session (context = B) but tries to insert a row tagged user_a.
    # WITH CHECK must reject it.
    async with session(user_b) as conn:
        with pytest.raises(Exception):
            await SourceRepository(conn).create(user_a, "json", "iso-cross")


@pytest.mark.asyncio
async def test_observations_isolated_between_tenants(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "pdf", "iso-obs")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "secret"}], src.id, user_a
        )

    async with session(user_b) as conn:
        b_view = await ObservationRepository(conn).list_for_source(src.id)
    assert b_view == []
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/kernel/test_tenant_isolation.py -v`
Expected: PASS (all three). If any FAIL, RLS is broken — revisit Task 3 (FORCE RLS, WITH CHECK) or Task 5 (set_config). Do not weaken the test.

- [ ] **Step 3: Run the full kernel suite with coverage**

Run: `pytest --cov=kernel --cov-report=term-missing`
Expected: all tests PASS, `kernel` coverage ≥ 80%

- [ ] **Step 4: Commit**

```bash
git add tests/kernel/test_tenant_isolation.py
git commit -m "test: cross-tenant rls isolation security gate"
```

---

## Self-Review

**Spec coverage (Plan 1 portion of the Phase 0 spec):**
- §2 Project structure (Python side) → Task 1 ✓
- §3 Docker Compose (postgres+redis) → Task 2 ✓ (backend/worker/frontend/caddy deferred to Plans 3–4, noted)
- §4 Schema, tables, UNIQUE constraint → Task 3 ✓
- §4 Two-role RLS, FORCE, USING+WITH CHECK, fail-closed → Tasks 3, 5, 9 ✓
- §4 `set_config(..., true)` transaction contract → Task 5 ✓
- Domain models → Task 4 ✓
- Repositories (sources, fragments, observations, jobs) → Tasks 6, 7, 8 ✓
- Tenant isolation invariants → Task 9 (security gate) ✓
- pgvector extension enabled → Task 3 ✓

**Deferred to later plans (correctly out of scope here):** parsers/normalizer (Plan 2), Dramatiq worker + FastAPI auth + endpoints (Plan 3), frontend (Plan 4), CI workflows (Plan 5). The `audit_logs` writes are exercised in Plan 3 where the worker and API create audit records.

**Placeholder scan:** none — every step contains runnable code or exact commands.

**Type consistency:** `Source.from_row`, `Fragment.from_row`, `Observation.from_row`, `Job.from_row` defined in Task 4 and consumed in Tasks 6–8. `session(user_id)` signature (Task 5) consumed identically in Tasks 6–9. Repository method names in the Interfaces blocks match the implementations.

**Note for executor:** Tasks 3, 5–9 require the Docker Postgres from Task 2 running, and two env vars exported:
```bash
export MIGRATION_DATABASE_URL="postgresql+asyncpg://locigraph:changeme@localhost:5432/locigraph"
export DATABASE_URL="postgresql+asyncpg://locigraph_app:changeme@localhost:5432/locigraph"
export APP_DB_PASSWORD="changeme"
```
