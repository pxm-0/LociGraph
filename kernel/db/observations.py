from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Observation

_COLUMNS = (
    "id, user_id, source_id, fragment_id, observed_at, speaker, "
    "content, confidence, status, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ObservationRepository(BaseRepository):
    async def bulk_insert(
        self, rows: list[dict[str, Any]], source_id: str | UUID, user_id: str | UUID
    ) -> list[UUID]:
        ids: list[UUID] = []
        for row in rows:
            new_id = (
                await self.conn.execute(
                    text(
                        """
                        INSERT INTO observations
                            (user_id, source_id, fragment_id, observed_at, speaker,
                             content, context_before, context_after, confidence)
                        VALUES (:user_id, :source_id, :fragment_id, :observed_at, :speaker,
                                :content, :ctx_before, :ctx_after, :confidence)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": str(user_id),
                        "source_id": str(source_id),
                        "fragment_id": row.get("fragment_id"),
                        "observed_at": row.get("observed_at"),
                        "speaker": row.get("speaker"),
                        "content": row["content"],
                        "ctx_before": row.get("context_before"),
                        "ctx_after": row.get("context_after"),
                        "confidence": row.get("confidence", 1.0),
                    },
                )
            ).scalar_one()
            ids.append(new_id)
        return ids

    async def list_for_source(self, source_id: str | UUID) -> list[Observation]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM observations "
                    "WHERE source_id = :sid ORDER BY created_at"
                ),
                {"sid": str(source_id)},
            )
        ).mappings().all()
        return [Observation.from_row(_as_mapping(r)) for r in rows]

    async def count_for_source(self, source_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text("SELECT count(*) FROM observations WHERE source_id = :sid"),
                {"sid": str(source_id)},
            )
        ).scalar_one()
        return result

    async def count(self) -> int:
        result: int = (
            await self.conn.execute(text("SELECT count(*) FROM observations"))
        ).scalar_one()
        return result

    async def list(
        self,
        *,
        source_id: str | UUID | None = None,
        speaker: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Observation]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if speaker is not None:
            clauses.append("speaker = :speaker")
            params["speaker"] = speaker
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM observations {where}"
                    " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [Observation.from_row(_as_mapping(r)) for r in rows]
