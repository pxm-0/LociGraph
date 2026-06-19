from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection


class BaseRepository:
    """Holds the RLS-scoped connection. Subclasses issue queries against it."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
