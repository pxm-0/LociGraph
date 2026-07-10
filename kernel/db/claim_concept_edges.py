from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import ClaimConceptEdge

_COLUMNS = (
    "id, user_id, claim_id, concept_id, concept_candidate_id, confidence, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ClaimConceptEdgeRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        claim_id: str | UUID,
        concept_id: str | UUID,
        concept_candidate_id: str | UUID,
        confidence: float,
    ) -> ClaimConceptEdge | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO claim_concept_edges
                        (user_id, claim_id, concept_id, concept_candidate_id, confidence)
                    VALUES
                        (:user_id, :claim_id, :concept_id, :concept_candidate_id, :confidence)
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "claim_id": str(claim_id),
                    "concept_id": str(concept_id),
                    "concept_candidate_id": str(concept_candidate_id),
                    "confidence": confidence,
                },
            )
        ).mappings().first()
        return ClaimConceptEdge.from_row(_as_mapping(row)) if row else None

    async def get(self, edge_id: str | UUID) -> ClaimConceptEdge | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM claim_concept_edges WHERE id = :id"),
                {"id": str(edge_id)},
            )
        ).mappings().first()
        return ClaimConceptEdge.from_row(_as_mapping(row)) if row else None

    async def list_for_claim(self, claim_id: str | UUID) -> list[ClaimConceptEdge]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM claim_concept_edges "
                    "WHERE claim_id = :claim_id ORDER BY created_at DESC"
                ),
                {"claim_id": str(claim_id)},
            )
        ).mappings().all()
        return [ClaimConceptEdge.from_row(_as_mapping(r)) for r in rows]

    async def list_for_concept(
        self, concept_id: str | UUID, limit: int | None = None
    ) -> list[ClaimConceptEdge]:
        params: dict[str, Any] = {"concept_id": str(concept_id)}
        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT :limit"
            params["limit"] = limit
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM claim_concept_edges "
                    f"WHERE concept_id = :concept_id ORDER BY created_at DESC{limit_clause}"
                ),
                params,
            )
        ).mappings().all()
        return [ClaimConceptEdge.from_row(_as_mapping(r)) for r in rows]
