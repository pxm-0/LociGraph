# Phase 0 — Plan 3: Async Pipeline & API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the data layer (Plan 1) and the ingestion kernel (Plan 2) into a working end-to-end pipeline behind an authenticated HTTP API: upload a file → a background worker parses + normalizes it → observations become queryable, all tenant-scoped by RLS.

**Architecture:** A thin **FastAPI** app (`backend/`) handles transport + JWT auth and submits background jobs. A **Dramatiq** worker (`worker/`) runs the `ingest_source` task, which drives the async kernel: `get_parser()` → `FragmentRepository` → `Normalizer` → `ObservationRepository`, all inside RLS-scoped sessions. Frontend/API share one origin (Caddy in prod, Next rewrites in dev). The kernel stays framework-free; backend and worker are shells around it.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Dramatiq + Redis, PyJWT, bcrypt, python-multipart, httpx (tests), plus the existing SQLAlchemy/asyncpg/Alembic kernel.

## Global Constraints

- Python floor **3.12**. App/worker connect as the non-owner role `locigraph_app`; RLS is enforced (Plan 1 invariants hold).
- Every DB query still goes through `kernel.db.session(user_id)` (the only connection doorway) — **except** auth's user lookup, which is pre-authentication and uses a non-tenant connection on the no-RLS `users` table (see Task 4 rationale).
- Auth: JWT **HS256**, secret from `JWT_SECRET`, `sub = user_id`, 7-day expiry. Cookie `locigraph_token`: `HttpOnly; SameSite=Lax; Secure` (Secure on in prod). Passwords hashed with **bcrypt**.
- Single origin, **no CORS**: browser talks only to the frontend origin; Caddy (prod) / Next rewrites (dev) proxy `/api/*` → backend.
- Upload requires an explicit `source_type` form field (one of `SourceType.ALL`) — extension alone can't distinguish ChatGPT vs Meta vs generic JSON.
- Dedup is enforced by the DB `UNIQUE (user_id, checksum_sha256)`; the API returns `409` on duplicate.
- `mypy --strict` clean on `kernel`, `backend`, `worker`; `ruff check kernel backend worker tests` clean; no bare `pytest.raises(Exception)`.
- Coverage ≥ **80%** on `kernel`, `backend`, `worker`.
- No secrets in code; all from env. Immutable domain models.

## Interface contracts from Plans 1–2 (do not redefine)

- `kernel.db.session(user_id)` → async ctx mgr yielding an RLS-scoped `AsyncConnection`.
- `kernel.db.engine.get_engine()` → app-role `AsyncEngine`; `dispose_engine()`.
- `SourceRepository`: `create(user_id, source_type, checksum_sha256, *, original_filename=, original_mime_type=, file_size_bytes=, raw_storage_path=) -> Source`; `get(id) -> Source|None`; `set_status(id, status)`; `mark_verified(id)`; `list(limit, offset) -> list[Source]`.
- `FragmentRepository.bulk_insert(rows, source_id, user_id) -> list[UUID]` (row keys: `raw_index, extracted_text, timestamp, author`).
- `ObservationRepository.bulk_insert(rows, source_id, user_id) -> list[UUID]` (row keys: `content, observed_at, speaker, fragment_id, context_before, context_after` — **`confidence` added in Task 2**); `list_for_source(id)`; `count_for_source(id)`.
- `JobRepository`: `create(user_id, job_type, *, payload=) -> Job`; `mark_running(id)`; `mark_completed(id, result=)`; `record_attempt(id, error)`; `get(id) -> Job|None`.
- `kernel.ingestion.registry.get_parser(source_type) -> Parser`; `Parser.parse(path) -> list[ParsedFragment]`; `ParsedFragment.to_fragment_row()`.
- `kernel.ingestion.normalizer.Normalizer().normalize(fragments) -> list[dict]` (keys incl. `confidence`).
- `kernel.ingestion.base.SourceType` (constants + `ALL`).

---

## File Structure

```
backend/
├── __init__.py                  # T1
└── app/
    ├── __init__.py              # T1
    ├── config.py                # T1  — Settings from env
    ├── main.py                  # T6  — FastAPI app, router wiring, lifespan
    ├── auth/
    │   ├── __init__.py          # T5
    │   ├── jwt.py               # T5  — create_token / decode_token
    │   └── dependencies.py      # T6  — get_current_user
    ├── jobs/
    │   ├── __init__.py          # T8
    │   └── submit.py            # T8  — enqueue ingest_source
    ├── api/
    │   ├── __init__.py          # T6
    │   ├── auth.py              # T6  — /auth/login, /auth/logout
    │   ├── sources.py           # T9  — /sources upload+list+get
    │   └── observations.py      # T10 — /observations
    └── scripts/
        ├── __init__.py          # T7
        └── init_user.py         # T7

worker/
├── __init__.py                  # T1
├── broker.py                    # T1  — Redis/Stub broker setup
├── main.py                      # T1  — worker entrypoint
└── tasks/
    ├── __init__.py              # T8
    └── ingest_source.py         # T8  — actor + async _ingest pipeline

kernel/
├── storage.py                   # T3  — save_raw (local fs, S3-swappable)
├── auth/
│   ├── __init__.py              # T4
│   └── passwords.py             # T4  — hash_password / verify_password
└── db/
    └── users.py                 # T4  — UserRepository (non-tenant)

tests/
├── backend/
│   ├── test_config.py           # T1
│   ├── test_jwt.py              # T5
│   ├── test_auth_api.py         # T6
│   ├── test_init_user.py        # T7
│   ├── test_sources_api.py      # T9
│   ├── test_observations_api.py # T10
│   └── conftest.py              # T6  — app client + auth fixtures
├── worker/
│   └── test_ingest_source.py    # T8
├── kernel/
│   ├── test_storage.py          # T3
│   ├── test_users_repository.py # T4
│   ├── test_passwords.py        # T4
│   └── test_observations_repository.py  # T2 (extend existing)
└── test_end_to_end.py           # T12

docker-compose.yml               # T11 — add backend, worker, caddy
backend/Dockerfile               # T11
worker/Dockerfile                # T11
Caddyfile                        # T11 — /api/* -> backend
```

---

### Task 1: Backend/worker scaffolding, deps, config, broker

**Files:** Create `backend/__init__.py`, `backend/app/__init__.py`, `backend/app/config.py`, `worker/__init__.py`, `worker/broker.py`, `worker/main.py`, `tests/backend/__init__.py`, `tests/backend/test_config.py`, `tests/worker/__init__.py`; Modify `pyproject.toml`.

**Interfaces produced:**
- `backend.app.config.Settings` with attrs `database_url, redis_url, jwt_secret, locigraph_email, locigraph_password, raw_storage_path, cookie_secure: bool`; classmethod `from_env() -> Settings`.
- `worker.broker.get_broker()` → the active Dramatiq broker (RedisBroker in normal use).

- [ ] **Step 1: Add deps to `pyproject.toml`**

Add to `[project].dependencies`:
```toml
    "fastapi>=0.111,<0.112",
    "uvicorn[standard]>=0.30,<0.31",
    "dramatiq[redis]>=1.17,<1.18",
    "pyjwt>=2.8,<2.10",
    "bcrypt>=4.1,<5.0",
    "python-multipart>=0.0.9,<0.0.10",
```
Add to `[project.optional-dependencies].dev`: `"httpx>=0.27,<0.28"`.
Change `[tool.setuptools.packages.find]` include to: `include = ["kernel*", "backend*", "worker*"]`.
Update `[tool.pytest.ini_options].addopts` coverage to: `--cov=kernel --cov=backend --cov=worker --cov-report=term-missing --import-mode=importlib`.
Then: `.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 2: Write the failing test**

`tests/backend/__init__.py`, `tests/worker/__init__.py`: do NOT create (importlib mode; no test packages). Create only the test file.

`tests/backend/test_config.py`:
```python
import os

from backend.app.config import Settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/y")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("LOCIGRAPH_EMAIL", "a@b.com")
    monkeypatch.setenv("LOCIGRAPH_PASSWORD", "pw")
    monkeypatch.setenv("RAW_STORAGE_PATH", "/data/raw")
    s = Settings.from_env()
    assert s.database_url == "postgresql+asyncpg://x/y"
    assert s.jwt_secret == "secret"
    assert s.cookie_secure is False  # default in non-prod


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    import pytest

    with pytest.raises(KeyError):
        Settings.from_env()
```

- [ ] **Step 3: Run test → RED** (`ModuleNotFoundError: backend`).
Run: `.venv/bin/pytest tests/backend/test_config.py -v`

- [ ] **Step 4: Implement**

`backend/__init__.py`, `backend/app/__init__.py`: docstring one-liners.

`backend/app/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    jwt_secret: str
    locigraph_email: str
    locigraph_password: str
    raw_storage_path: str
    cookie_secure: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ["DATABASE_URL"],
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
            jwt_secret=os.environ["JWT_SECRET"],
            locigraph_email=os.environ["LOCIGRAPH_EMAIL"],
            locigraph_password=os.environ["LOCIGRAPH_PASSWORD"],
            raw_storage_path=os.environ.get("RAW_STORAGE_PATH", "/data/raw"),
            cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        )
```

`worker/__init__.py`: docstring.

`worker/broker.py`:
```python
from __future__ import annotations

import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker

_broker: dramatiq.Broker | None = None


def get_broker() -> dramatiq.Broker:
    global _broker
    if _broker is None:
        _broker = RedisBroker(url=os.environ.get("REDIS_URL", "redis://localhost:6379"))
        dramatiq.set_broker(_broker)
    return _broker
```

`worker/main.py`:
```python
"""Worker entrypoint: `dramatiq worker.main`. Imports tasks so actors register."""
from worker.broker import get_broker

get_broker()

from worker.tasks import ingest_source  # noqa: E402,F401  (registers the actor)
```
> Note: `worker.tasks.ingest_source` is created in Task 8. Until then, `worker/main.py`'s import will fail if run — that's fine; it's not imported by tests in Task 1. (The Task 1 test only imports `backend.app.config`.)

- [ ] **Step 5: Run test → GREEN.** `.venv/bin/pytest tests/backend/test_config.py -v`
- [ ] **Step 6: Lint/type your files.** `.venv/bin/ruff check backend tests/backend && .venv/bin/mypy backend`
- [ ] **Step 7: Commit.** `git add pyproject.toml backend/ worker/__init__.py worker/broker.py worker/main.py tests/backend/test_config.py` then `git commit -m "chore: backend/worker scaffolding, settings, dramatiq broker"`

---

### Task 2: ObservationRepository persists `confidence`

**Files:** Modify `kernel/db/observations.py`; Modify `tests/kernel/test_observations_repository.py` (extend) — note the existing test file is `tests/kernel/test_fragments_observations_repository.py`; add the new test there.

**Why:** Plan 2 review found the `Normalizer` emits `confidence` but `ObservationRepository.bulk_insert` never inserts it (relying on the column DEFAULT 1.0). Wire it through so non-default confidence persists.

**Interfaces:** `ObservationRepository.bulk_insert` now reads `row.get("confidence", 1.0)` and includes it in the INSERT.

- [ ] **Step 1: Add failing test** to `tests/kernel/test_fragments_observations_repository.py`:
```python
@pytest.mark.asyncio
async def test_bulk_insert_persists_confidence(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "json", "c-conf-1")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "x", "confidence": 0.5}], src.id, user_id
        )
        obs = await ObservationRepository(conn).list_for_source(src.id)
    assert obs[0].confidence == 0.5
```
(Imports `SourceRepository`, `ObservationRepository`, `session` already present in the file.)

- [ ] **Step 2: Run → RED** (confidence comes back 1.0, assert fails).
Run: `.venv/bin/pytest tests/kernel/test_fragments_observations_repository.py::test_bulk_insert_persists_confidence -v` (export DB env first).

- [ ] **Step 3: Implement** — in `kernel/db/observations.py` `bulk_insert`, add `confidence` to the INSERT column list and values, and the param: `"confidence": row.get("confidence", 1.0)`. The INSERT becomes:
```python
INSERT INTO observations
    (user_id, source_id, fragment_id, observed_at, speaker,
     content, context_before, context_after, confidence)
VALUES (:user_id, :source_id, :fragment_id, :observed_at, :speaker,
        :content, :ctx_before, :ctx_after, :confidence)
RETURNING id
```
- [ ] **Step 4: Run → GREEN.** Re-run the test.
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check kernel/db/observations.py && .venv/bin/mypy kernel`
- [ ] **Step 6: Commit.** `git add kernel/db/observations.py tests/kernel/test_fragments_observations_repository.py` then `git commit -m "fix: persist observation confidence in bulk_insert"`

---

### Task 3: Storage adapter

**Files:** Create `kernel/storage.py`, `tests/kernel/test_storage.py`.

**Interfaces:** `save_raw(root: Path, user_id, source_id, filename: str, data: bytes) -> str` — writes `data` to `root/<user_id>/<source_id>/<safe_filename>` (creating dirs), returns the absolute path as a string. `safe_filename` strips path separators (`os.path.basename`).

- [ ] **Step 1: Failing test** `tests/kernel/test_storage.py`:
```python
import uuid
from pathlib import Path

from kernel.storage import save_raw


def test_save_raw_writes_under_user_and_source(tmp_path):
    uid, sid = uuid.uuid4(), uuid.uuid4()
    p = save_raw(tmp_path, uid, sid, "notes.md", b"hello")
    written = Path(p)
    assert written.read_bytes() == b"hello"
    assert str(uid) in p and str(sid) in p
    assert written.name == "notes.md"


def test_save_raw_strips_path_traversal(tmp_path):
    uid, sid = uuid.uuid4(), uuid.uuid4()
    p = save_raw(tmp_path, uid, sid, "../../etc/passwd", b"x")
    assert Path(p).name == "passwd"
    assert "/etc/passwd" not in p
```
- [ ] **Step 2: Run → RED.** `.venv/bin/pytest tests/kernel/test_storage.py -v` (no DB needed).
- [ ] **Step 3: Implement** `kernel/storage.py`:
```python
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID


def save_raw(root: Path, user_id: str | UUID, source_id: str | UUID,
             filename: str, data: bytes) -> str:
    safe = os.path.basename(filename) or "upload"
    target_dir = Path(root) / str(user_id) / str(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe
    target.write_bytes(data)
    return str(target)
```
- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check kernel/storage.py tests/kernel/test_storage.py && .venv/bin/mypy kernel`
- [ ] **Step 6: Commit.** `git add kernel/storage.py tests/kernel/test_storage.py` then `git commit -m "feat: local raw-file storage adapter"`

---

### Task 4: UserRepository + password hashing

**Files:** Create `kernel/auth/__init__.py`, `kernel/auth/passwords.py`, `kernel/db/users.py`, `tests/kernel/test_passwords.py`, `tests/kernel/test_users_repository.py`.

**Design note (users + RLS):** Login looks up a user **by email before any identity is known**, so it cannot run inside a tenant-scoped `session(user_id)`. The `users` table therefore intentionally has **no RLS** (as built in Plan 1) and is reached only by the auth layer over a plain app-role connection. This resolves the Plan 1 follow-up: full users-RLS is incompatible with pre-auth lookup; `audit_logs` RLS is deferred until audit writes exist (Phase 1+).

**Interfaces:**
- `kernel.auth.passwords.hash_password(pw: str) -> str`; `verify_password(pw: str, hashed: str) -> bool` (bcrypt).
- `kernel.db.users.UserRepository`: constructed with an `AsyncConnection`; `create(email, password_hash) -> User`; `get_by_email(email) -> User | None`; `get(user_id) -> User | None`. (Runs on a non-tenant connection — `users` has no RLS.)

- [ ] **Step 1: Failing tests**

`tests/kernel/test_passwords.py`:
```python
from kernel.auth.passwords import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong", h) is False
```

`tests/kernel/test_users_repository.py`:
```python
import uuid

import pytest
from sqlalchemy import text

from kernel.auth.passwords import hash_password
from kernel.db.engine import get_engine
from kernel.db.users import UserRepository


@pytest.mark.asyncio
async def test_create_and_get_by_email():
    engine = get_engine()
    email = f"{uuid.uuid4()}@example.com"
    async with engine.begin() as conn:  # non-tenant: users has no RLS
        repo = UserRepository(conn)
        created = await repo.create(email, hash_password("pw"))
        fetched = await repo.get_by_email(email)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.email == email
    # cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": created.id})
```
> This test needs `DATABASE_URL`. It does not use `make_user`, so it manages its own cleanup. (Add a module-level skip-if-no-DB is unnecessary — the suite always runs with DB env.)

- [ ] **Step 2: Run → RED.** `.venv/bin/pytest tests/kernel/test_passwords.py tests/kernel/test_users_repository.py -v` (export DB env).
- [ ] **Step 3: Implement**

`kernel/auth/__init__.py`: docstring.

`kernel/auth/passwords.py`:
```python
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())
```

`kernel/db/users.py`:
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.models import User

_COLUMNS = "id, email, created_at"


class UserRepository:
    """Accesses the no-RLS `users` table on a plain (non-tenant) connection."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def create(self, email: str, password_hash: str) -> User:
        row = (await self.conn.execute(
            text(f"INSERT INTO users (email, password_hash) "
                 f"VALUES (:email, :ph) RETURNING {_COLUMNS}"),
            {"email": email, "ph": password_hash},
        )).mappings().one()
        return User.from_row(row)

    async def get_by_email(self, email: str) -> User | None:
        row = (await self.conn.execute(
            text(f"SELECT {_COLUMNS} FROM users WHERE email = :email"),
            {"email": email},
        )).mappings().first()
        return User.from_row(row) if row else None

    async def get(self, user_id: str | UUID) -> User | None:
        row = (await self.conn.execute(
            text(f"SELECT {_COLUMNS} FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )).mappings().first()
        return User.from_row(row) if row else None

    async def verify_password_hash(self, email: str) -> str | None:
        row = (await self.conn.execute(
            text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": email},
        )).mappings().first()
        return row["password_hash"] if row else None
```
> `User.from_row` (Plan 1) reads `id, email, created_at` — matches `_COLUMNS`. `password_hash` is fetched separately via `verify_password_hash` so it never rides on the `User` model.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check kernel/auth kernel/db/users.py tests/kernel/test_passwords.py tests/kernel/test_users_repository.py && .venv/bin/mypy kernel`
- [ ] **Step 6: Commit.** `git add kernel/auth kernel/db/users.py tests/kernel/test_passwords.py tests/kernel/test_users_repository.py` then `git commit -m "feat: user repository and bcrypt password hashing"`

---

### Task 5: JWT module

**Files:** Create `backend/app/auth/__init__.py`, `backend/app/auth/jwt.py`, `tests/backend/test_jwt.py`.

**Interfaces:** `create_token(user_id: str, secret: str, *, now: datetime, ttl_days: int = 7) -> str`; `decode_token(token: str, secret: str) -> str` (returns `sub`/user_id; raises `InvalidTokenError` on bad/expired). `now` is injected so tests are deterministic.

- [ ] **Step 1: Failing test** `tests/backend/test_jwt.py`:
```python
from datetime import UTC, datetime, timedelta

import pytest
from jwt import InvalidTokenError

from backend.app.auth.jwt import create_token, decode_token

SECRET = "test-secret"


def test_roundtrip():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = create_token("user-123", SECRET, now=now)
    assert decode_token(token, SECRET) == "user-123"


def test_expired_token_rejected():
    past = datetime(2020, 1, 1, tzinfo=UTC)
    token = create_token("u", SECRET, now=past, ttl_days=1)
    with pytest.raises(InvalidTokenError):
        decode_token(token, SECRET)


def test_wrong_secret_rejected():
    token = create_token("u", SECRET, now=datetime.now(UTC))
    with pytest.raises(InvalidTokenError):
        decode_token(token, "other-secret")
```
- [ ] **Step 2: Run → RED.** `.venv/bin/pytest tests/backend/test_jwt.py -v` (no DB).
- [ ] **Step 3: Implement** `backend/app/auth/__init__.py` (docstring) and `backend/app/auth/jwt.py`:
```python
from __future__ import annotations

from datetime import datetime, timedelta

import jwt

_ALG = "HS256"


def create_token(user_id: str, secret: str, *, now: datetime, ttl_days: int = 7) -> str:
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(days=ttl_days)}
    return jwt.encode(payload, secret, algorithm=_ALG)


def decode_token(token: str, secret: str) -> str:
    payload = jwt.decode(token, secret, algorithms=[_ALG])
    return str(payload["sub"])
```
- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check backend/app/auth tests/backend/test_jwt.py && .venv/bin/mypy backend`
- [ ] **Step 6: Commit.** `git add backend/app/auth/__init__.py backend/app/auth/jwt.py tests/backend/test_jwt.py` then `git commit -m "feat: jwt create/decode"`

---

### Task 6: FastAPI app, auth dependency, login/logout

**Files:** Create `backend/app/main.py`, `backend/app/auth/dependencies.py`, `backend/app/api/__init__.py`, `backend/app/api/auth.py`, `tests/backend/conftest.py`, `tests/backend/test_auth_api.py`.

**Interfaces:**
- `backend.app.main.create_app() -> FastAPI` and module-level `app = create_app()`.
- `get_current_user(request) -> str` FastAPI dependency: reads `locigraph_token` cookie, decodes, returns `user_id`; raises `HTTPException(401)` if missing/invalid.
- `POST /auth/login` body `{"password": str}` → verify against the configured user (by `LOCIGRAPH_EMAIL`) → set cookie → `{"user_id": ...}`. `POST /auth/logout` → clear cookie.

- [ ] **Step 1: conftest + failing test**

`tests/backend/conftest.py`:
```python
import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.auth.passwords import hash_password
from kernel.db.engine import dispose_engine, get_engine


@pytest_asyncio.fixture(autouse=True)
async def _reset_engine():
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def seeded_user(_reset_engine):
    """Insert the configured login user; clean up after."""
    email = os.environ["LOCIGRAPH_EMAIL"]
    uid = uuid.uuid4()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        await conn.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id,:e,:ph)"),
            {"id": uid, "e": email, "ph": hash_password(os.environ["LOCIGRAPH_PASSWORD"])},
        )
    yield uid
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})


@pytest_asyncio.fixture
async def client():
    from backend.app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

`tests/backend/test_auth_api.py`:
```python
import os

import pytest


@pytest.mark.asyncio
async def test_login_sets_cookie_and_logout_clears(client, seeded_user):
    r = await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})
    assert r.status_code == 200
    assert r.json()["user_id"] == str(seeded_user)
    assert "locigraph_token" in r.cookies

    r2 = await client.post("/auth/logout")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_401(client, seeded_user):
    r = await client.post("/auth/login", json={"password": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_cookie(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401
```

- [ ] **Step 2: Run → RED.** `.venv/bin/pytest tests/backend/test_auth_api.py -v` (export DB + auth env).
- [ ] **Step 3: Implement**

`backend/app/auth/dependencies.py`:
```python
from __future__ import annotations

from fastapi import HTTPException, Request
from jwt import InvalidTokenError

from backend.app.auth.jwt import decode_token
from backend.app.config import Settings


def get_current_user(request: Request) -> str:
    token = request.cookies.get("locigraph_token")
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return decode_token(token, Settings.from_env().jwt_secret)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token") from None
```

`backend/app/api/__init__.py`: docstring.

`backend/app/api/auth.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt import create_token
from backend.app.config import Settings
from kernel.auth.passwords import verify_password
from kernel.db.engine import get_engine
from kernel.db.users import UserRepository

router = APIRouter()


class LoginBody(BaseModel):
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, response: Response) -> dict[str, str]:
    settings = Settings.from_env()
    engine = get_engine()
    async with engine.begin() as conn:
        repo = UserRepository(conn)
        user = await repo.get_by_email(settings.locigraph_email)
        stored_hash = await repo.verify_password_hash(settings.locigraph_email)
    if user is None or stored_hash is None or not verify_password(body.password, stored_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_token(str(user.id), settings.jwt_secret, now=datetime.now(timezone.utc))
    response.set_cookie(
        "locigraph_token", token, httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/",
    )
    return {"user_id": str(user.id)}


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("locigraph_token", path="/")
    return {"status": "logged out"}


@router.get("/auth/me")
async def me(user_id: str = Depends(get_current_user)) -> dict[str, str]:
    return {"user_id": user_id}
```

`backend/app/main.py`:
```python
from __future__ import annotations

from fastapi import FastAPI

from backend.app.api import auth


def create_app() -> FastAPI:
    app = FastAPI(title="LociGraph")
    app.include_router(auth.router)
    return app


app = create_app()
```
- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check backend tests/backend && .venv/bin/mypy backend`
- [ ] **Step 6: Commit.** `git add backend/app/main.py backend/app/auth/dependencies.py backend/app/api/__init__.py backend/app/api/auth.py tests/backend/conftest.py tests/backend/test_auth_api.py` then `git commit -m "feat: fastapi app, jwt cookie auth, login/logout"`

---

### Task 7: init_user script

**Files:** Create `backend/app/scripts/__init__.py`, `backend/app/scripts/init_user.py`, `tests/backend/test_init_user.py`.

**Interfaces:** `init_user() -> bool` — idempotently ensures a user row for `LOCIGRAPH_EMAIL` with a bcrypt hash of `LOCIGRAPH_PASSWORD`; returns `True` if created, `False` if it already existed. Runnable via `python -m backend.app.scripts.init_user`.

- [ ] **Step 1: Failing test** `tests/backend/test_init_user.py`:
```python
import os
import uuid

import pytest
from sqlalchemy import text

from backend.app.scripts.init_user import init_user
from kernel.db.engine import get_engine


@pytest.mark.asyncio
async def test_init_user_is_idempotent(monkeypatch):
    email = f"{uuid.uuid4()}@example.com"
    monkeypatch.setenv("LOCIGRAPH_EMAIL", email)
    monkeypatch.setenv("LOCIGRAPH_PASSWORD", "pw")
    try:
        assert await init_user() is True   # created
        assert await init_user() is False  # already exists
    finally:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
```
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `backend/app/scripts/__init__.py` (docstring) and `backend/app/scripts/init_user.py`:
```python
from __future__ import annotations

import asyncio

from backend.app.config import Settings
from kernel.auth.passwords import hash_password
from kernel.db.engine import get_engine
from kernel.db.users import UserRepository


async def init_user() -> bool:
    settings = Settings.from_env()
    engine = get_engine()
    async with engine.begin() as conn:
        repo = UserRepository(conn)
        if await repo.get_by_email(settings.locigraph_email) is not None:
            return False
        await repo.create(settings.locigraph_email, hash_password(settings.locigraph_password))
        return True


if __name__ == "__main__":
    created = asyncio.run(init_user())
    print("created" if created else "already exists")
```
- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check backend/app/scripts tests/backend/test_init_user.py && .venv/bin/mypy backend`
- [ ] **Step 6: Commit.** `git add backend/app/scripts tests/backend/test_init_user.py` then `git commit -m "feat: idempotent init_user script"`

---

### Task 8: Job submission + `ingest_source` worker pipeline

**Files:** Create `backend/app/jobs/__init__.py`, `backend/app/jobs/submit.py`, `worker/tasks/__init__.py`, `worker/tasks/ingest_source.py`, `tests/worker/test_ingest_source.py`.

**Interfaces:**
- `worker.tasks.ingest_source.ingest_source` — Dramatiq actor `(source_id: str, user_id: str, job_id: str)`; thin sync wrapper calling `asyncio.run(_ingest(...))`.
- `worker.tasks.ingest_source._ingest(source_id, user_id, job_id, source_type, raw_path)` — the async pipeline (tested directly).
- `backend.app.jobs.submit.submit_ingest(source_id, user_id, job_id, source_type, raw_path)` — calls `ingest_source.send(...)`.

> The actor signature carries only ids; `_ingest` re-reads the source for `source_type`/`raw_storage_path` inside an RLS session. The unit test calls `_ingest` directly (no live broker), exercising the full parser→normalize→persist path against the real DB.

- [ ] **Step 1: Failing test** `tests/worker/test_ingest_source.py`:
```python
import pytest

from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.ingest_source import _ingest


@pytest.mark.asyncio
async def test_ingest_parses_and_persists_observations(make_user, tmp_path):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('[{"text":"alpha"},{"text":"beta"}]', encoding="utf-8")

    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "e2e-1", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    await _ingest(str(src.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        refreshed = await SourceRepository(conn).get(src.id)
        count = await ObservationRepository(conn).count_for_source(src.id)
        done = await JobRepository(conn).get(job.id)
    assert refreshed.import_status == "VERIFIED"
    assert count == 2
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_ingest_is_idempotent(make_user, tmp_path):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('["x"]', encoding="utf-8")
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "json", "e2e-2", raw_storage_path=str(raw))
        job = await JobRepository(conn).create(user_id, "ingest_source")
    await _ingest(str(src.id), str(user_id), str(job.id))
    await _ingest(str(src.id), str(user_id), str(job.id))  # second run must not double-insert
    async with session(user_id) as conn:
        count = await ObservationRepository(conn).count_for_source(src.id)
    assert count == 1
```
- [ ] **Step 2: Run → RED** (`ModuleNotFoundError: worker.tasks.ingest_source`).
- [ ] **Step 3: Implement**

`worker/tasks/__init__.py`: docstring.

`worker/tasks/ingest_source.py`:
```python
from __future__ import annotations

import asyncio
from pathlib import Path

import dramatiq

from kernel.db.fragments import FragmentRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.ingestion.normalizer import Normalizer
from kernel.ingestion.registry import get_parser
from worker.broker import get_broker

get_broker()  # ensure a broker is set before the actor is declared


async def _ingest(source_id: str, user_id: str, job_id: str) -> None:
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        await SourceRepository(conn).set_status(source_id, "INGESTING")

    try:
        async with session(user_id) as conn:
            source = await SourceRepository(conn).get(source_id)
            if source is None:
                raise ValueError(f"source {source_id} not found")
            # Idempotency: skip if observations already exist for this source.
            if await ObservationRepository(conn).count_for_source(source_id) > 0:
                await SourceRepository(conn).mark_verified(source_id)
                await JobRepository(conn).mark_completed(job_id, result={"skipped": True})
                return

            fragments = get_parser(source.source_type).parse(Path(source.raw_storage_path))
            await FragmentRepository(conn).bulk_insert(
                [f.to_fragment_row() for f in fragments], source_id, user_id
            )
            rows = Normalizer().normalize(fragments)
            await ObservationRepository(conn).bulk_insert(rows, source_id, user_id)
            await SourceRepository(conn).mark_verified(source_id)
            await JobRepository(conn).mark_completed(job_id, result={"observations": len(rows)})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=str(exc))
            await SourceRepository(conn).set_status(source_id, "FAILED")
        raise


@dramatiq.actor(queue_name="ingestion", max_retries=3)
def ingest_source(source_id: str, user_id: str, job_id: str) -> None:
    asyncio.run(_ingest(source_id, user_id, job_id))
```

`backend/app/jobs/__init__.py`: docstring.

`backend/app/jobs/submit.py`:
```python
from __future__ import annotations

from worker.tasks.ingest_source import ingest_source


def submit_ingest(source_id: str, user_id: str, job_id: str) -> None:
    ingest_source.send(source_id, user_id, job_id)
```
- [ ] **Step 4: Run → GREEN.** `.venv/bin/pytest tests/worker/test_ingest_source.py -v` (DB env; no running worker needed — `_ingest` is called directly).
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check worker backend/app/jobs tests/worker && .venv/bin/mypy worker backend`
- [ ] **Step 6: Commit.** `git add worker/tasks backend/app/jobs tests/worker/test_ingest_source.py` then `git commit -m "feat: ingest_source worker pipeline (parse -> normalize -> persist)"`

---

### Task 9: Sources endpoints (upload, list, get)

**Files:** Create `backend/app/api/sources.py`, `tests/backend/test_sources_api.py`; Modify `backend/app/main.py` (include router).

**Interfaces:**
- `POST /sources/upload` — multipart `source_type` (form) + `file` — validates `source_type ∈ SourceType.ALL`, reads bytes, computes SHA-256, creates a `sources` row (`PENDING`) + a `jobs` row, stores the file, enqueues `ingest_source`. Returns `202 {source_id, status}`. `409` on duplicate checksum; `400` on bad source_type.
- `GET /sources` — current user's sources, newest first. `GET /sources/{id}` — one source (for polling).

> **Test isolation from the broker:** the test overrides the `submit_ingest` dependency (or monkeypatches `backend.app.api.sources.submit_ingest`) with a no-op recorder, so uploading doesn't require a running Redis/worker — it asserts the rows are created and the job is enqueued.

- [ ] **Step 1: Failing test** `tests/backend/test_sources_api.py`:
```python
import os

import pytest

from kernel.db.engine import get_engine
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.app.api.sources.submit_ingest",
        lambda *a, **k: calls.append(a),
    )
    return calls


async def _login(client):
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_upload_creates_pending_source_and_enqueues(client, seeded_user, _no_broker):
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("a.json", b'[{"text":"hi"}]', "application/json")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "PENDING"
    assert len(_no_broker) == 1  # enqueued exactly once
    # cleanup
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM jobs WHERE user_id = :u"), {"u": str(seeded_user)})
        await conn.execute(text("DELETE FROM sources WHERE user_id = :u"), {"u": str(seeded_user)})


@pytest.mark.asyncio
async def test_duplicate_checksum_returns_409(client, seeded_user, _no_broker):
    await _login(client)
    payload = {"data": {"source_type": "json"},
               "files": {"file": ("a.json", b'["x"]', "application/json")}}
    r1 = await client.post("/sources/upload", **payload)
    r2 = await client.post("/sources/upload", **payload)
    assert r1.status_code == 202
    assert r2.status_code == 409
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM jobs WHERE user_id = :u"), {"u": str(seeded_user)})
        await conn.execute(text("DELETE FROM sources WHERE user_id = :u"), {"u": str(seeded_user)})


@pytest.mark.asyncio
async def test_bad_source_type_returns_400(client, seeded_user, _no_broker):
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "bogus"},
        files={"file": ("a.json", b"[]", "application/json")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_auth(client, _no_broker):
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("a.json", b"[]", "application/json")},
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** `backend/app/api/sources.py`:
```python
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings
from backend.app.jobs.submit import submit_ingest
from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.ingestion.base import SourceType
from kernel.storage import save_raw

router = APIRouter()


@router.post("/sources/upload", status_code=202)
async def upload_source(
    source_type: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    if source_type not in SourceType.ALL:
        raise HTTPException(status_code=400, detail=f"invalid source_type: {source_type}")
    data = await file.read()
    checksum = hashlib.sha256(data).hexdigest()
    try:
        async with session(user_id) as conn:
            source = await SourceRepository(conn).create(
                user_id, source_type, checksum,
                original_filename=file.filename,
                original_mime_type=file.content_type,
                file_size_bytes=len(data),
            )
            path = save_raw(
                Path(Settings.from_env().raw_storage_path),
                user_id, source.id, file.filename or "upload", data,
            )
            await SourceRepository(conn).update_storage_path(source.id, path)
            job = await JobRepository(conn).create(
                user_id, "ingest_source", payload={"source_id": str(source.id)}
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="duplicate source (checksum)") from None

    submit_ingest(str(source.id), str(user_id), str(job.id))
    return {"source_id": str(source.id), "status": "PENDING"}


@router.get("/sources")
async def list_sources(user_id: str = Depends(get_current_user)) -> list[dict]:
    async with session(user_id) as conn:
        sources = await SourceRepository(conn).list()
    return [_serialize(s) for s in sources]


@router.get("/sources/{source_id}")
async def get_source(source_id: str, user_id: str = Depends(get_current_user)) -> dict:
    async with session(user_id) as conn:
        source = await SourceRepository(conn).get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="not found")
    return _serialize(source)


def _serialize(s) -> dict:
    return {
        "id": str(s.id), "source_type": s.source_type,
        "original_filename": s.original_filename,
        "import_status": s.import_status,
        "file_size_bytes": s.file_size_bytes,
    }
```
> Requires a new repo method `SourceRepository.update_storage_path(source_id, path)` (one-line `UPDATE sources SET raw_storage_path=:p WHERE id=:id`). Add it to `kernel/db/sources.py` in this task and cover it in the existing `test_sources_repository.py`.

Register the router in `backend/app/main.py`: `from backend.app.api import auth, sources` and `app.include_router(sources.router)`.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check backend kernel/db/sources.py tests/backend && .venv/bin/mypy backend kernel`
- [ ] **Step 6: Commit.** `git add backend/app/api/sources.py backend/app/main.py kernel/db/sources.py tests/backend/test_sources_api.py tests/kernel/test_sources_repository.py` then `git commit -m "feat: source upload/list/get endpoints"`

---

### Task 10: Observations endpoint

**Files:** Create `backend/app/api/observations.py`, `tests/backend/test_observations_api.py`; Modify `backend/app/main.py` (include router); Modify `kernel/db/observations.py` (add a filtered list method).

**Interfaces:**
- `ObservationRepository.list(*, source_id=None, speaker=None, status=None, limit=50, offset=0) -> list[Observation]` — tenant-scoped, optional filters.
- `GET /observations?source_id=&speaker=&status=&limit=&offset=` → current user's observations.

- [ ] **Step 1: Failing test** `tests/backend/test_observations_api.py`:
```python
import os

import pytest
from sqlalchemy import text

from kernel.db.engine import get_engine
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_list_observations_for_current_user(client, seeded_user):
    async with session(str(seeded_user)) as conn:
        src = await SourceRepository(conn).create(str(seeded_user), "json", "obs-api-1")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "hello"}, {"content": "world"}], src.id, str(seeded_user)
        )
    await _login(client)
    r = await client.get("/observations")
    assert r.status_code == 200
    contents = {o["content"] for o in r.json()}
    assert {"hello", "world"} <= contents

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM observations WHERE user_id=:u"), {"u": str(seeded_user)})
        await conn.execute(text("DELETE FROM sources WHERE user_id=:u"), {"u": str(seeded_user)})


@pytest.mark.asyncio
async def test_observations_requires_auth(client):
    r = await client.get("/observations")
    assert r.status_code == 401
```
- [ ] **Step 2: Run → RED.**
- [ ] **Step 3: Implement** the repo `list` method in `kernel/db/observations.py` (tenant-scoped SELECT with dynamic `AND` filters, all bound params), and `backend/app/api/observations.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from kernel.db.observations import ObservationRepository
from kernel.db.session import session

router = APIRouter()


@router.get("/observations")
async def list_observations(
    source_id: str | None = None,
    speaker: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[dict]:
    async with session(user_id) as conn:
        obs = await ObservationRepository(conn).list(
            source_id=source_id, speaker=speaker, status=status, limit=limit, offset=offset
        )
    return [
        {"id": str(o.id), "content": o.content, "speaker": o.speaker,
         "observed_at": o.observed_at.isoformat() if o.observed_at else None,
         "confidence": o.confidence, "source_id": str(o.source_id) if o.source_id else None}
        for o in obs
    ]
```
Register in `main.py`. Add a repo test for the filtered `list` in `tests/kernel/test_fragments_observations_repository.py`.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Lint/type.** `.venv/bin/ruff check backend kernel/db/observations.py tests && .venv/bin/mypy backend kernel`
- [ ] **Step 6: Commit.** `git add backend/app/api/observations.py backend/app/main.py kernel/db/observations.py tests/backend/test_observations_api.py tests/kernel/test_fragments_observations_repository.py` then `git commit -m "feat: observations list endpoint with filters"`

---

### Task 11: Docker Compose + Caddy wiring

**Files:** Create `backend/Dockerfile`, `worker/Dockerfile`; Modify `docker-compose.yml`, `Caddyfile`.

**Interfaces:** `docker compose up` brings up postgres, redis, backend (uvicorn), worker (dramatiq), caddy. Caddy routes `/api/*` → backend `:8000`. (Frontend service is added in Plan 4.)

- [ ] **Step 1: `backend/Dockerfile`**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY kernel ./kernel
COPY backend ./backend
COPY worker ./worker
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir -e .
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- [ ] **Step 2: `worker/Dockerfile`** — same base/install, `CMD ["dramatiq", "worker.main", "--processes", "1", "--threads", "2"]`.
- [ ] **Step 3: Add services to `docker-compose.yml`** (backend, worker, caddy) with env: `DATABASE_URL` (app role), `MIGRATION_DATABASE_URL` (owner, backend only), `REDIS_URL`, `JWT_SECRET`, `LOCIGRAPH_EMAIL/PASSWORD`, `APP_DB_PASSWORD`, `RAW_STORAGE_PATH=/data/raw`, `COOKIE_SECURE=true` (prod). Mount a `raw_data` volume at `/data/raw` on backend + worker. Add `redis` healthcheck (`redis-cli ping`) and `start_period` on postgres (closes Plan 1 Minor findings). Backend depends_on postgres+redis healthy; worker likewise.
- [ ] **Step 4: `Caddyfile`** — replace the placeholder:
```
:80 {
	handle /api/* {
		uri strip_prefix /api
		reverse_proxy backend:8000
	}
	respond "LociGraph API gateway" 200
}
```
(Frontend handler added in Plan 4.)
- [ ] **Step 5: Verify** — `docker compose config` (valid), then `docker compose up -d --build backend worker` and check both start; `curl -s localhost:8000/auth/me` → 401 (app is up). Run `docker compose exec backend python -m backend.app.scripts.init_user`.
- [ ] **Step 6: Commit.** `git add backend/Dockerfile worker/Dockerfile docker-compose.yml Caddyfile` then `git commit -m "chore: dockerize backend+worker, caddy /api routing"`

---

### Task 12: End-to-end test (capstone)

**Files:** Create `tests/test_end_to_end.py`.

**Interfaces:** none (test only). Proves the whole slice: upload via the API → run the worker pipeline → poll status VERIFIED → observations queryable.

- [ ] **Step 1: Write the test** `tests/test_end_to_end.py`:
```python
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.auth.passwords import hash_password
from kernel.db.engine import dispose_engine, get_engine
from worker.tasks.ingest_source import _ingest


@pytest.mark.asyncio
async def test_upload_then_ingest_then_query(monkeypatch):
    email = os.environ["LOCIGRAPH_EMAIL"]
    # seed the login user
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email})
        await conn.execute(
            text("INSERT INTO users (email, password_hash) VALUES (:e,:p)"),
            {"e": email, "p": hash_password(os.environ["LOCIGRAPH_PASSWORD"])},
        )

    captured = {}
    monkeypatch.setattr(
        "backend.app.api.sources.submit_ingest",
        lambda sid, uid, jid: captured.update(sid=sid, uid=uid, jid=jid),
    )

    from backend.app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})
        up = await ac.post(
            "/sources/upload",
            data={"source_type": "json"},
            files={"file": ("c.json", b'[{"text":"gamma"},{"text":"delta"}]', "application/json")},
        )
        assert up.status_code == 202

        # run the worker pipeline directly (no live broker in tests)
        await _ingest(captured["sid"], captured["uid"], captured["jid"])

        status = await ac.get(f"/sources/{captured['sid']}")
        assert status.json()["import_status"] == "VERIFIED"

        obs = await ac.get("/observations")
        contents = {o["content"] for o in obs.json()}
    assert "gamma" in contents and "delta" in contents

    # cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM observations WHERE user_id IN (SELECT id FROM users WHERE email=:e)"), {"e": email})
        await conn.execute(text("DELETE FROM fragments WHERE user_id IN (SELECT id FROM users WHERE email=:e)"), {"e": email})
        await conn.execute(text("DELETE FROM jobs WHERE user_id IN (SELECT id FROM users WHERE email=:e)"), {"e": email})
        await conn.execute(text("DELETE FROM sources WHERE user_id IN (SELECT id FROM users WHERE email=:e)"), {"e": email})
        await conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email})
    await dispose_engine()
```
- [ ] **Step 2: Run → it should pass once Tasks 1–10 are in.** `.venv/bin/pytest tests/test_end_to_end.py -v` (DB env + auth env).
- [ ] **Step 3: Full suite + coverage.** `.venv/bin/pytest -q` → all pass; coverage ≥ 80% on kernel/backend/worker. `.venv/bin/ruff check kernel backend worker tests && .venv/bin/mypy kernel backend worker`.
- [ ] **Step 4: Commit.** `git add tests/test_end_to_end.py` then `git commit -m "test: end-to-end upload -> ingest -> query"`

---

## Self-Review

**Spec coverage (Phase 0 spec §5 Auth, §6 Ingestion API/worker):**
- JWT login/logout, httpOnly cookie, middleware/dependency → Tasks 5, 6 ✓
- init_user → Task 7 ✓
- Async job queue (Dramatiq+Redis), `ingest_source` task, status transitions, jobs ledger → Tasks 1, 8 ✓
- Upload (mime/type validate, checksum dedup, storage, enqueue), list, get → Tasks 3, 9 ✓
- Observations endpoint → Task 10 ✓
- Same-origin/Caddy, dockerized services → Task 11 ✓
- Confidence persisted (Plan 2 follow-up) → Task 2 ✓
- End-to-end proof → Task 12 ✓

**Decisions baked in (flag for review):**
- **bcrypt directly** (not passlib) — fewer moving parts, no passlib/bcrypt version-skew warnings.
- **Upload requires an explicit `source_type` form field** — extension can't separate ChatGPT/Meta/generic JSON.
- **`users` stays un-RLS'd**; auth reads it on a non-tenant connection (login is pre-auth). `audit_logs` RLS deferred until audit writes exist (Phase 1+). This is the considered resolution of the Plan 1 "add users/audit RLS" follow-up.
- **Worker tested by calling `_ingest` directly** (no live broker in tests); endpoints stub `submit_ingest`. A real broker only runs in Docker (Task 11).
- **Plain `Settings`** from env (no pydantic-settings) to minimize deps.
- **No new migration** — schema from Plan 1 already has every column; Task 2 is a repo change only.

**Out of scope (later):** frontend (Plan 4), CI (Plan 5), streaming-to-disk for very large uploads (reads fully into memory in Phase 0 — fine for expected sizes; revisit if needed), source quarantine/purge job, audit_logs writes/RLS.

**Placeholder scan:** none — every step has runnable code or exact commands. **Type/interface consistency:** repo signatures match Plans 1–2; `_ingest` signature is consistent between the actor, `submit_ingest`, and the tests; `get_current_user` returns `user_id: str` consumed identically across endpoints.

**Note for executor:** Tasks 2, 4, 6–10, 12 need Postgres running and env exported (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `APP_DB_PASSWORD`, plus `JWT_SECRET`, `LOCIGRAPH_EMAIL`, `LOCIGRAPH_PASSWORD`). Tasks 1, 3, 5 are pure (no DB). Task 11 needs Docker.
```
