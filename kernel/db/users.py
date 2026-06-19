from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.models import User

_COLUMNS = "id, email, created_at"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    """Cast a SQLAlchemy RowMapping to the plain Mapping[str, Any] expected by models."""
    return row  # type: ignore[return-value]


class UserRepository:
    """Accesses the no-RLS `users` table on a plain (non-tenant) connection."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def create(self, email: str, password_hash: str) -> User:
        row = (await self.conn.execute(
            text(f"INSERT INTO users (email, password_hash) "
                 f"VALUES (:email, :ph) RETURNING {_COLUMNS}"),
            {"email": email, "ph": password_hash},
        )).mappings().one()
        return User.from_row(_as_mapping(row))

    async def get_by_email(self, email: str) -> User | None:
        row = (await self.conn.execute(
            text(f"SELECT {_COLUMNS} FROM users WHERE email = :email"),
            {"email": email},
        )).mappings().first()
        return User.from_row(_as_mapping(row)) if row else None

    async def get(self, user_id: str | UUID) -> User | None:
        row = (await self.conn.execute(
            text(f"SELECT {_COLUMNS} FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )).mappings().first()
        return User.from_row(_as_mapping(row)) if row else None

    async def verify_password_hash(self, email: str) -> str | None:
        row = (await self.conn.execute(
            text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": email},
        )).mappings().first()
        return row["password_hash"] if row else None
