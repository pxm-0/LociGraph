from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Contradiction

_COLUMNS = (
    "id, user_id, concept_id, claim_a_id, claim_b_id, similarity, "
    "classification, rationale, created_at, classified_at"
)

CLASSIFICATIONS = {"true_conflict", "evolution", "contextual_difference", "both"}


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ContradictionRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        concept_id: str | UUID,
        claim_a_id: str | UUID,
        claim_b_id: str | UUID,
        similarity: float,
        rationale: str,
    ) -> Contradiction | None:
        a_id, b_id = sorted([str(claim_a_id), str(claim_b_id)])
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO contradictions
                        (user_id, concept_id, claim_a_id, claim_b_id, similarity, rationale)
                    VALUES
                        (:user_id, :concept_id, :claim_a_id, :claim_b_id, :similarity, :rationale)
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "concept_id": str(concept_id),
                    "claim_a_id": a_id,
                    "claim_b_id": b_id,
                    "similarity": similarity,
                    "rationale": strip_nul_bytes(rationale),
                },
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None

    async def get(self, contradiction_id: str | UUID) -> Contradiction | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM contradictions WHERE id = :id"),
                {"id": str(contradiction_id)},
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None

    async def list(
        self,
        *,
        concept_id: str | UUID | None = None,
        classification: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Contradiction]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if concept_id is not None:
            clauses.append("concept_id = :concept_id")
            params["concept_id"] = str(concept_id)
        if classification is not None:
            clauses.append("classification = :classification")
            params["classification"] = classification
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM contradictions {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [Contradiction.from_row(_as_mapping(r)) for r in rows]

    async def list_for_concepts(
        self, concept_ids: Sequence[str | UUID]
    ) -> builtins.list[Contradiction]:
        if not concept_ids:
            return []
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM contradictions WHERE concept_id = ANY(:concept_ids) "
                    "ORDER BY created_at DESC"
                ),
                {"concept_ids": [str(c) for c in concept_ids]},
            )
        ).mappings().all()
        return [Contradiction.from_row(_as_mapping(r)) for r in rows]

    async def count(
        self,
        *,
        concept_id: str | UUID | None = None,
        classification: str | None = None,
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if concept_id is not None:
            clauses.append("concept_id = :concept_id")
            params["concept_id"] = str(concept_id)
        if classification is not None:
            clauses.append("classification = :classification")
            params["classification"] = classification
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        result: int = (
            await self.conn.execute(
                text(f"SELECT count(*) FROM contradictions {where}"), params
            )
        ).scalar_one()
        return result

    async def classify(
        self, contradiction_id: str | UUID, classification: str
    ) -> Contradiction | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE contradictions
                    SET classification = :classification, classified_at = now()
                    WHERE id = :id
                    RETURNING {_COLUMNS}
                    """
                ),
                {"id": str(contradiction_id), "classification": classification},
            )
        ).mappings().first()
        return Contradiction.from_row(_as_mapping(row)) if row else None
