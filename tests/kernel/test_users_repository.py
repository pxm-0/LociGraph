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
