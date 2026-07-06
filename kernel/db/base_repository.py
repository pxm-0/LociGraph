from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection


def strip_nul_bytes(value: Any) -> Any:
    """Postgres' UTF8 encoding rejects embedded NUL bytes (raw or \\u0000-escaped
    in JSON) — strip them from LLM-extracted text before it hits an INSERT."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: strip_nul_bytes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_nul_bytes(v) for v in value]
    return value


class BaseRepository:
    """Holds the RLS-scoped connection. Subclasses issue queries against it."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
