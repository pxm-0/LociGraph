"""Re-embed a user's existing semantic_vectors with the current embedding model.

Maintenance tool: run after changing OPENAI_EMBEDDING_MODEL so existing vectors
move into the new model's space. Vectors from different models are not
comparable (cosine similarity across them is meaningless), so a mixed table
degrades contradiction detection until every row shares one model.

Idempotent + resumable: only rows whose model_name differs from the configured
target are touched, and each batch commits on its own, so a re-run continues
where an interrupted run stopped.

Usage:
    python -m backend.app.scripts.reembed_backfill <user_id> [batch_size]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.session import session

DEFAULT_BATCH = 1000


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def _embed_with_retry(embedder, texts, tries: int = 4):
    for attempt in range(tries):
        try:
            return await embedder.embed(texts)
        except Exception as exc:  # transient (rate limit / network) — back off
            if attempt == tries - 1:
                raise
            wait = 2**attempt
            print(f"embed error: {exc}; retry in {wait}s", flush=True)
            await asyncio.sleep(wait)


async def reembed(user_id: str, batch: int = DEFAULT_BATCH) -> int:
    settings = EmbeddingSettings.from_env()
    model = settings.openai_embedding_model
    embedder = get_embedder(settings)

    async with session(user_id) as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT sv.claim_id, c.claim_text FROM semantic_vectors sv "
                    "JOIN claims c ON c.id = sv.claim_id WHERE sv.model_name <> :m"
                ),
                {"m": model},
            )
        ).all()

    total = len(rows)
    print(
        f"re-embedding {total} rows -> {model} (dims={settings.embedding_dimensions})",
        flush=True,
    )
    done = 0
    for start in range(0, total, batch):
        chunk = rows[start : start + batch]
        vectors = await _embed_with_retry(embedder, [r[1] for r in chunk])
        params = [
            {"emb": _vector_literal(v), "m": model, "cid": str(cid)}
            for (cid, _), v in zip(chunk, vectors, strict=True)
        ]
        async with session(user_id) as conn:
            await conn.execute(
                text(
                    "UPDATE semantic_vectors SET embedding = CAST(:emb AS vector), "
                    "model_name = :m WHERE claim_id = :cid"
                ),
                params,
            )
        done += len(chunk)
        print(f"{done}/{total}", flush=True)
    print("DONE", flush=True)
    return total


def _main() -> None:
    args = sys.argv[1:]
    if not args:
        print(
            "usage: python -m backend.app.scripts.reembed_backfill <user_id> [batch_size]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    user_id = args[0]
    batch = int(args[1]) if len(args) > 1 else DEFAULT_BATCH
    asyncio.run(reembed(user_id, batch))


if __name__ == "__main__":
    _main()
