import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from kernel.auth.passwords import hash_password
from kernel.db.engine import get_engine
from kernel.db.session import session


@pytest_asyncio.fixture
async def seeded_user(reset_engine):
    """Insert the configured login user; clean up after."""
    email = os.environ["LOCIGRAPH_EMAIL"]
    uid = uuid.uuid4()
    engine = get_engine()
    # Use migration role (bypasses FORCE RLS) to clean up any orphaned rows from
    # previous failed runs before inserting the fresh user.
    migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    if migration_url:
        mig_engine = create_async_engine(migration_url, pool_pre_ping=True)
        async with mig_engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM jobs WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :e)"
                ),
                {"e": email},
            )
            await conn.execute(
                text(
                    "DELETE FROM sources WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :e)"
                ),
                {"e": email},
            )
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        await mig_engine.dispose()
    else:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id,:e,:ph)"),
            {"id": uid, "e": email, "ph": hash_password(os.environ["LOCIGRAPH_PASSWORD"])},
        )
    yield uid
    # Teardown: remove owned rows (FK-protected) then the user itself.
    async with session(uid) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})


@pytest_asyncio.fixture
async def client():
    from backend.app.main import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
