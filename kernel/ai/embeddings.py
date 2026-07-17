from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    active_ai_provider: str
    openai_api_key: str | None
    openai_embedding_model: str
    embedding_dimensions: int
    embedding_autorun: bool
    embedding_batch_size: int

    @classmethod
    def from_env(cls) -> EmbeddingSettings:
        return cls(
            active_ai_provider=os.environ.get("ACTIVE_AI_PROVIDER", "openai"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            # ponytail: 3-large @ 1536 dims beats 3-small @ 1536 (MTEB) with no
            # schema change — the vector(1536) column + HNSW index stay valid.
            # Peak recall needs dims=3072 → ALTER column + index rebuild + re-embed.
            openai_embedding_model=os.environ.get(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
            ),
            embedding_dimensions=max(1, int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))),
            embedding_autorun=os.environ.get("EMBEDDING_AUTORUN", "false").lower() == "true",
            embedding_batch_size=max(1, int(os.environ.get("EMBEDDING_BATCH_SIZE", "100"))),
        )


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self.dimensions
        )
        return [item.embedding for item in response.data]


def get_embedder(settings: EmbeddingSettings | None = None) -> OpenAIEmbedder:
    settings = settings or EmbeddingSettings.from_env()
    if settings.active_ai_provider != "openai":
        raise ValueError(f"unsupported ACTIVE_AI_PROVIDER: {settings.active_ai_provider}")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when ACTIVE_AI_PROVIDER=openai")
    return OpenAIEmbedder(
        settings.openai_api_key, settings.openai_embedding_model, settings.embedding_dimensions
    )
