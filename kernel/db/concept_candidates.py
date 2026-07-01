from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import ConceptCandidate

_COLUMNS = (
    "id, user_id, source_id, claim_id, candidate_name, concept_type, rationale, "
    "confidence, extraction_method, model_name, prompt_version, status, created_at, metadata"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ConceptCandidateRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        source_id: str | UUID,
        claim_id: str | UUID,
        candidate_name: str,
        concept_type: str,
        rationale: str | None,
        confidence: float,
        extraction_method: str,
        model_name: str | None,
        prompt_version: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> ConceptCandidate:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO concept_candidates
                        (user_id, source_id, claim_id, candidate_name, concept_type,
                         rationale, confidence, extraction_method, model_name,
                         prompt_version, metadata)
                    VALUES
                        (:user_id, :source_id, :claim_id, :candidate_name, :concept_type,
                         :rationale, :confidence, :extraction_method, :model_name,
                         :prompt_version, CAST(:metadata AS JSONB))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_id": str(source_id),
                    "claim_id": str(claim_id),
                    "candidate_name": candidate_name,
                    "concept_type": concept_type,
                    "rationale": rationale,
                    "confidence": confidence,
                    "extraction_method": extraction_method,
                    "model_name": model_name,
                    "prompt_version": prompt_version,
                    "metadata": json.dumps(metadata or {}),
                },
            )
        ).mappings().one()
        return ConceptCandidate.from_row(_as_mapping(row))

    async def get(self, candidate_id: str | UUID) -> ConceptCandidate | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM concept_candidates WHERE id = :id"),
                {"id": str(candidate_id)},
            )
        ).mappings().first()
        return ConceptCandidate.from_row(_as_mapping(row)) if row else None

    async def mark_status(
        self, candidate_id: str | UUID, *, from_status: str, to_status: str
    ) -> ConceptCandidate | None:
        """Transition status only if currently `from_status`. Returns the
        updated row, or None if the candidate doesn't exist / isn't in
        `from_status` (RLS makes cross-tenant rows invisible too). Shared by
        `reject` and by kernel/concepts_promotion.py's approve orchestration."""
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE concept_candidates
                    SET status = :to_status
                    WHERE id = :id AND status = :from_status
                    RETURNING {_COLUMNS}
                    """
                ),
                {"id": str(candidate_id), "from_status": from_status, "to_status": to_status},
            )
        ).mappings().first()
        return ConceptCandidate.from_row(_as_mapping(row)) if row else None

    async def reject(self, candidate_id: str | UUID) -> ConceptCandidate | None:
        """Status transition only: proposed -> rejected. No concept or edge
        involved. Returns None if the candidate is missing, not visible to
        this tenant, or not currently `proposed` (Task 3/API decides how to
        surface that as a 404 vs 409)."""
        return await self.mark_status(candidate_id, from_status="proposed", to_status="rejected")

    async def list(
        self,
        *,
        source_id: str | UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConceptCandidate]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM concept_candidates {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [ConceptCandidate.from_row(_as_mapping(r)) for r in rows]

    async def count_for_source(self, source_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text("SELECT count(*) FROM concept_candidates WHERE source_id = :source_id"),
                {"source_id": str(source_id)},
            )
        ).scalar_one()
        return result
