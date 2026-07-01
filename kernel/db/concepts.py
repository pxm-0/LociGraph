from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Concept

_COLUMNS = "id, user_id, concept_name, concept_type, description, status, created_at, metadata"


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ConceptRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        concept_name: str,
        concept_type: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Concept | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO concepts
                        (user_id, concept_name, concept_type, description, metadata)
                    VALUES
                        (:user_id, :concept_name, :concept_type, :description,
                         CAST(:metadata AS JSONB))
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "concept_name": concept_name,
                    "concept_type": concept_type,
                    "description": description,
                    "metadata": json.dumps(metadata or {}),
                },
            )
        ).mappings().first()
        return Concept.from_row(_as_mapping(row)) if row else None

    async def get(self, concept_id: str | UUID) -> Concept | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM concepts WHERE id = :id"),
                {"id": str(concept_id)},
            )
        ).mappings().first()
        return Concept.from_row(_as_mapping(row)) if row else None

    async def find_by_name(self, concept_type: str, concept_name: str) -> Concept | None:
        row = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM concepts "
                    "WHERE concept_type = :concept_type "
                    "AND lower(concept_name) = lower(:concept_name)"
                ),
                {"concept_type": concept_type, "concept_name": concept_name},
            )
        ).mappings().first()
        return Concept.from_row(_as_mapping(row)) if row else None

    async def list(
        self,
        *,
        concept_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Concept]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if concept_type is not None:
            clauses.append("concept_type = :concept_type")
            params["concept_type"] = concept_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM concepts {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [Concept.from_row(_as_mapping(r)) for r in rows]
