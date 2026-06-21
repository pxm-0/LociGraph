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
