from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Revision

_COLUMNS = (
    "id, user_id, concept_id, contradiction_id, source, "
    "previous_description, new_description, rationale, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class RevisionRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        concept_id: str | UUID,
        contradiction_id: str | UUID | None,
        source: str,
        previous_description: str | None,
        new_description: str,
        rationale: str | None,
    ) -> Revision:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO revisions
                        (user_id, concept_id, contradiction_id, source,
                         previous_description, new_description, rationale)
                    VALUES
                        (:user_id, :concept_id, :contradiction_id, :source,
                         :previous_description, :new_description, :rationale)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "concept_id": str(concept_id),
                    "contradiction_id": str(contradiction_id) if contradiction_id else None,
                    "source": source,
                    "previous_description": previous_description,
                    "new_description": strip_nul_bytes(new_description),
                    "rationale": strip_nul_bytes(rationale),
                },
            )
        ).mappings().one()
        return Revision.from_row(_as_mapping(row))

    async def get(self, revision_id: str | UUID) -> Revision | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM revisions WHERE id = :id"),
                {"id": str(revision_id)},
            )
        ).mappings().first()
        return Revision.from_row(_as_mapping(row)) if row else None

    async def list(
        self, *, concept_id: str | UUID, limit: int = 50, offset: int = 0
    ) -> list[Revision]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM revisions WHERE concept_id = :concept_id "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"concept_id": str(concept_id), "limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Revision.from_row(_as_mapping(r)) for r in rows]

    async def count(self, *, concept_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text("SELECT count(*) FROM revisions WHERE concept_id = :concept_id"),
                {"concept_id": str(concept_id)},
            )
        ).scalar_one()
        return result
