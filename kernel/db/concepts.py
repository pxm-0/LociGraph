from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
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

    async def update_description(
        self, concept_id: str | UUID, new_description: str
    ) -> Concept | None:
        row = (
            await self.conn.execute(
                text(
                    f"UPDATE concepts SET description = :description WHERE id = :id "
                    f"RETURNING {_COLUMNS}"
                ),
                {"id": str(concept_id), "description": strip_nul_bytes(new_description)},
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

    async def find_or_create(
        self,
        *,
        user_id: str | UUID,
        concept_type: str,
        concept_name: str,
        description: str | None = None,
    ) -> Concept:
        """Case-insensitive dedup within (user_id, concept_type): return the
        existing concept if one matches by name, else create it. RLS scopes
        find_by_name to the current user, so a concurrent insert by the same
        user racing this call is the only conflict case `create` can hit —
        handled by re-fetching on the None (conflict) result."""
        existing = await self.find_by_name(concept_type, concept_name)
        if existing is not None:
            return existing
        created = await self.create(
            user_id=user_id,
            concept_name=concept_name,
            concept_type=concept_type,
            description=description,
        )
        if created is not None:
            return created
        existing = await self.find_by_name(concept_type, concept_name)
        assert existing is not None, "create() conflicted but no matching row found"
        return existing

    async def count_for_concept(self, concept_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text(
                    "SELECT count(*) FROM claim_concept_edges WHERE concept_id = :concept_id"
                ),
                {"concept_id": str(concept_id)},
            )
        ).scalar_one()
        return result

    async def count(
        self, *, concept_type: str | None = None, status: str | None = None
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if concept_type is not None:
            clauses.append("concept_type = :concept_type")
            params["concept_type"] = concept_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        result: int = (
            await self.conn.execute(text(f"SELECT count(*) FROM concepts {where}"), params)
        ).scalar_one()
        return result

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

    async def search_by_name(self, query: str, limit: int = 5) -> list[Concept]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM concepts WHERE concept_name ILIKE :pattern "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"pattern": f"%{query}%", "limit": limit},
            )
        ).mappings().all()
        return [Concept.from_row(_as_mapping(r)) for r in rows]
