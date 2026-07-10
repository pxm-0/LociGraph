from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import ImportanceSignal

IMPORTANCE_TARGET_TYPES = {"claim", "concept", "observation"}

_COLUMNS = "id, user_id, target_type, target_id, created_at"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ImportanceSignalRepository(BaseRepository):
    async def create(
        self, *, user_id: str | UUID, target_type: str, target_id: str | UUID
    ) -> ImportanceSignal:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO importance_signals (user_id, target_type, target_id)
                    VALUES (:user_id, :target_type, :target_id)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "target_type": target_type,
                    "target_id": str(target_id),
                },
            )
        ).mappings().one()
        return ImportanceSignal.from_row(_as_mapping(row))

    async def list_for_target(
        self, target_type: str, target_id: str | UUID, limit: int = 50
    ) -> list[ImportanceSignal]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM importance_signals "
                    "WHERE target_type = :target_type AND target_id = :target_id "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"target_type": target_type, "target_id": str(target_id), "limit": limit},
            )
        ).mappings().all()
        return [ImportanceSignal.from_row(_as_mapping(r)) for r in rows]
