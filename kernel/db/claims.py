from __future__ import annotations

import builtins
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import Claim

_COLUMNS = (
    "id, user_id, source_id, observation_id, claim_text, claim_type, assertion_type, "
    "confidence, extraction_method, model_name, prompt_version, status, created_at, metadata"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class ClaimRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        source_id: str | UUID,
        observation_id: str | UUID,
        claim_text: str,
        claim_type: str,
        assertion_type: str,
        confidence: float,
        extraction_method: str,
        model_name: str | None,
        prompt_version: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> Claim | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO claims
                        (user_id, source_id, observation_id, claim_text, claim_type,
                         assertion_type, confidence, extraction_method, model_name,
                         prompt_version, metadata)
                    VALUES
                        (:user_id, :source_id, :observation_id, :claim_text, :claim_type,
                         :assertion_type, :confidence, :extraction_method, :model_name,
                         :prompt_version, CAST(:metadata AS JSONB))
                    ON CONFLICT DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_id": str(source_id),
                    "observation_id": str(observation_id),
                    "claim_text": strip_nul_bytes(claim_text),
                    "claim_type": claim_type,
                    "assertion_type": assertion_type,
                    "confidence": confidence,
                    "extraction_method": extraction_method,
                    "model_name": model_name,
                    "prompt_version": prompt_version,
                    "metadata": json.dumps(strip_nul_bytes(metadata or {})),
                },
            )
        ).mappings().first()
        return Claim.from_row(_as_mapping(row)) if row else None

    async def get(self, claim_id: str | UUID) -> Claim | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM claims WHERE id = :id"),
                {"id": str(claim_id)},
            )
        ).mappings().first()
        return Claim.from_row(_as_mapping(row)) if row else None

    async def list(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        assertion_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Claim]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if assertion_type is not None:
            clauses.append("assertion_type = :assertion_type")
            params["assertion_type"] = assertion_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM claims {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        ).mappings().all()
        return [Claim.from_row(_as_mapping(r)) for r in rows]

    async def count_for_source(self, source_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text("SELECT count(*) FROM claims WHERE source_id = :source_id"),
                {"source_id": str(source_id)},
            )
        ).scalar_one()
        return result

    async def list_for_source(self, source_id: str | UUID) -> builtins.list[Claim]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM claims WHERE source_id = :source_id "
                    "ORDER BY created_at"
                ),
                {"source_id": str(source_id)},
            )
        ).mappings().all()
        return [Claim.from_row(_as_mapping(r)) for r in rows]

    async def count(
        self,
        *,
        source_id: str | UUID | None = None,
        observation_id: str | UUID | None = None,
        claim_type: str | None = None,
        assertion_type: str | None = None,
        status: str | None = None,
    ) -> int:
        clauses = []
        params: dict[str, Any] = {}
        if source_id is not None:
            clauses.append("source_id = :source_id")
            params["source_id"] = str(source_id)
        if observation_id is not None:
            clauses.append("observation_id = :observation_id")
            params["observation_id"] = str(observation_id)
        if claim_type is not None:
            clauses.append("claim_type = :claim_type")
            params["claim_type"] = claim_type
        if assertion_type is not None:
            clauses.append("assertion_type = :assertion_type")
            params["assertion_type"] = assertion_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        result: int = (
            await self.conn.execute(text(f"SELECT count(*) FROM claims {where}"), params)
        ).scalar_one()
        return result

    async def observation_ids_with_live_claims(self, source_id: str | UUID) -> set[UUID]:
        rows = (
            await self.conn.execute(
                text(
                    "SELECT DISTINCT observation_id FROM claims "
                    "WHERE source_id = :source_id AND status IN ('proposed', 'accepted')"
                ),
                {"source_id": str(source_id)},
            )
        ).all()
        return {row[0] for row in rows}

    async def delete_proposed_for_source(self, source_id: str | UUID) -> None:
        # Candidates get auto-promoted (see worker/tasks/extract_claims.py),
        # which links them into claim_concept_edges — those edges must go
        # first, or the FK from claim_concept_edges to claims/concept_candidates
        # blocks the deletes below. The linked concepts themselves are left
        # alone: find_or_create may have reused one across other claims/sources.
        await self.conn.execute(
            text(
                "DELETE FROM claim_concept_edges WHERE claim_id IN "
                "(SELECT id FROM claims WHERE source_id = :source_id AND status = 'proposed')"
            ),
            {"source_id": str(source_id)},
        )
        await self.conn.execute(
            text(
                "DELETE FROM concept_candidates WHERE claim_id IN "
                "(SELECT id FROM claims WHERE source_id = :source_id AND status = 'proposed')"
            ),
            {"source_id": str(source_id)},
        )
        await self.conn.execute(
            text("DELETE FROM claims WHERE source_id = :source_id AND status = 'proposed'"),
            {"source_id": str(source_id)},
        )
