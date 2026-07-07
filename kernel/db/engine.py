from __future__ import annotations

import os
import threading

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_local = threading.local()


def get_engine() -> AsyncEngine:
    """Return an async engine private to the calling thread, connecting as the
    app (non-owner) role.

    A pooled asyncpg connection is bound to the event loop that opened it.
    The worker runs many actors concurrently across threads (--threads N),
    each via its own asyncio.run() call (a fresh loop every time), so a
    single process-wide engine hands out connections across loop boundaries
    and raises "attached to a different loop". Scoping the engine per thread
    keeps every connection scoped to the loop that will actually use it.
    """
    engine: AsyncEngine | None = getattr(_local, "engine", None)
    if engine is None:
        url = os.environ["DATABASE_URL"]
        engine = create_async_engine(url, pool_pre_ping=True)
        _local.engine = engine
    return engine


async def dispose_engine() -> None:
    engine: AsyncEngine | None = getattr(_local, "engine", None)
    if engine is not None:
        await engine.dispose()
        _local.engine = None
