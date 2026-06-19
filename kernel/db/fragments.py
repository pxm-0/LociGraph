from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Fragment

_COLUMNS = "id, user_id, source_id, raw_index, extracted_text, timestamp, author"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class FragmentRepository(BaseRepository):
    async def bulk_insert(
        self, rows: list[dict[str, Any]], source_id: str | UUID, user_id: str | UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for row in rows:
            new_id = (
                await self.conn.execute(
                    text(
                        """
                        INSERT INTO fragments
                            (user_id, source_id, raw_index, extracted_text, timestamp, author)
                        VALUES (:user_id, :source_id, :raw_index, :text, :ts, :author)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "source_id": str(source_id),
                        "raw_index": row.get("raw_index"),
                        "text": row.get("extracted_text"),
                        "ts": row.get("timestamp"),
                        "author": row.get("author"),
                    },
                )
            ).scalar_one()
            ids.append(new_id)
        return ids

    async def list_for_source(self, source_id: str | UUID) -> list[Fragment]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM fragments "
                    "WHERE source_id = :sid ORDER BY raw_index"
                ),
                {"sid": str(source_id)},
            )
        ).mappings().all()
        return [Fragment.from_row(_as_mapping(r)) for r in rows]
