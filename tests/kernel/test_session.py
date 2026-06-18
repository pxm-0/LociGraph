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
