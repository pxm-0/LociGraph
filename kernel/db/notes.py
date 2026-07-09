from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Note

_COLUMNS = "id, user_id, content, created_at"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class NoteRepository(BaseRepository):
    async def create(self, *, user_id: str | UUID, content: str) -> Note:
        row = (
            await self.conn.execute(
                text(
                    f"INSERT INTO notes (user_id, content) VALUES (:user_id, :content) "
                    f"RETURNING {_COLUMNS}"
                ),
                {"user_id": str(user_id), "content": strip_nul_bytes(content)},
            )
        ).mappings().one()
        return Note.from_row(_as_mapping(row))

    async def get(self, note_id: str | UUID) -> Note | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM notes WHERE id = :id"), {"id": str(note_id)}
            )
        ).mappings().first()
        return Note.from_row(_as_mapping(row)) if row else None

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[Note]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM notes ORDER BY created_at DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Note.from_row(_as_mapping(r)) for r in rows]
