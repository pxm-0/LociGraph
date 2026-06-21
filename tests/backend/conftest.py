import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.auth.passwords import hash_password
from kernel.db.engine import get_engine


@pytest_asyncio.fixture
async def seeded_user(reset_engine):
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
