from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.api.concepts import serialize_claim
from backend.app.auth.dependencies import get_current_user
from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session

router = APIRouter()


@router.get("/search")
async def search_claims(
    q: str,
    limit: int = 20,
    user_id: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    embedder = get_embedder(EmbeddingSettings.from_env())
    [query_embedding] = await embedder.embed([q])
    async with session(user_id) as conn:
        results = await SemanticVectorRepository(conn).search_similar(query_embedding, limit=limit)
    return [{**serialize_claim(r.claim), "similarity": r.similarity} for r in results]
