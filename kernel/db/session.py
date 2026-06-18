from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
