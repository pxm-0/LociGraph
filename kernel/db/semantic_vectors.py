from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Claim, SemanticVector, SimilarClaim

_COLUMNS = "id, user_id, claim_id, model_name, created_at, embedding::text AS embedding"

_CLAIM_COLUMNS = (
    "c.id, c.user_id, c.source_id, c.observation_id, c.claim_text, c.claim_type, "
    "c.assertion_type, c.confidence, c.extraction_method, c.model_name, c.prompt_version, "
    "c.status, c.created_at, c.metadata"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


def _embedding_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class SemanticVectorRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        claim_id: str | UUID,
        embedding: list[float],
        model_name: str,
    ) -> SemanticVector | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO semantic_vectors (user_id, claim_id, embedding, model_name)
                    VALUES (:user_id, :claim_id, CAST(:embedding AS vector), :model_name)
                    ON CONFLICT (claim_id) DO NOTHING
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "claim_id": str(claim_id),
                    "embedding": _embedding_literal(embedding),
                    "model_name": model_name,
                },
            )
        ).mappings().first()
        return SemanticVector.from_row(_as_mapping(row)) if row else None

    async def get_for_claim(self, claim_id: str | UUID) -> SemanticVector | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM semantic_vectors WHERE claim_id = :claim_id"),
                {"claim_id": str(claim_id)},
            )
        ).mappings().first()
        return SemanticVector.from_row(_as_mapping(row)) if row else None

    async def claim_ids_without_vector(self, source_id: str | UUID) -> set[UUID]:
        rows = (
            await self.conn.execute(
                text(
                    "SELECT c.id FROM claims c "
                    "LEFT JOIN semantic_vectors sv ON sv.claim_id = c.id "
                    "WHERE c.source_id = :source_id AND sv.id IS NULL"
                ),
                {"source_id": str(source_id)},
            )
        ).all()
        return {row[0] for row in rows}

    async def search_similar(
        self, query_embedding: list[float], limit: int = 20
    ) -> list[SimilarClaim]:
        rows = (
            await self.conn.execute(
                text(
                    f"""
                    SELECT {_CLAIM_COLUMNS},
                           1 - (sv.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                    FROM semantic_vectors sv
                    JOIN claims c ON c.id = sv.claim_id
                    ORDER BY sv.embedding <=> CAST(:query_embedding AS vector) ASC
                    LIMIT :limit
                    """
                ),
                {"query_embedding": _embedding_literal(query_embedding), "limit": limit},
            )
        ).mappings().all()
        return [
            SimilarClaim(claim=Claim.from_row(_as_mapping(r)), similarity=float(r["similarity"]))
            for r in rows
        ]
