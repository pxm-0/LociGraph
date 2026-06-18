import os
import uuid

import pytest_asyncio
from sqlalchemy import text

from kernel.db.engine import dispose_engine, get_engine
from kernel.db.session import session


@pytest_asyncio.fixture(autouse=True)
async def reset_engine():
    """Dispose the singleton engine after each async test so the next test's
    event loop gets a fresh pool — avoids 'Future attached to a different loop'."""
    yield
    await dispose_engine()


# Depends on reset_engine so its DELETE teardown runs before the engine is disposed.
@pytest_asyncio.fixture
async def make_user(reset_engine):
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
