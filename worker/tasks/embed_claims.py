from __future__ import annotations

from itertools import batched
from typing import Any

import dramatiq

from kernel.ai.embeddings import EmbeddingSettings, get_embedder
from kernel.db.claims import ClaimRepository
from kernel.db.jobs import JobRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

get_broker()


async def _embed_claims(source_id: str, user_id: str, job_id: str) -> None:
    settings = EmbeddingSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        vector_repo = SemanticVectorRepository(conn)
        pending_ids = await vector_repo.claim_ids_without_vector(source_id)
        if not pending_ids:
            await JobRepository(conn).mark_completed(job_id, result={"embedded": 0})
            return
        all_claims = await ClaimRepository(conn).list_for_source(source_id)
        pending_claims = [c for c in all_claims if c.id in pending_ids]

    async with session(user_id) as conn:
        await JobRepository(conn).update_progress(
            job_id, items_completed=0, items_total=len(pending_claims)
        )

    try:
        embedder = get_embedder(settings)
        embedded_count = 0
        processed_count = 0
        for batch in batched(pending_claims, settings.embedding_batch_size):
            vectors = await embedder.embed([c.claim_text for c in batch])
            async with session(user_id) as conn:
                vector_repo = SemanticVectorRepository(conn)
                for claim, vector in zip(batch, vectors, strict=True):
                    created = await vector_repo.create(
                        user_id=user_id,
                        claim_id=claim.id,
                        embedding=vector,
                        model_name=settings.openai_embedding_model,
                    )
                    if created is not None:
                        embedded_count += 1
                processed_count += len(batch)
                await JobRepository(conn).update_progress(
                    job_id, items_completed=processed_count, items_total=len(pending_claims)
                )

        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id, result={"embedded": embedded_count}
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


# Embedding a batch is one cheap OpenAI call (no per-item reasoning like claim
# extraction) — an hour comfortably covers even a large source's worth of
# batches without needing extraction's 3-hour ceiling.
EMBED_CLAIMS_TIME_LIMIT_MS = 60 * 60 * 1000


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_embed_claims",
    time_limit=EMBED_CLAIMS_TIME_LIMIT_MS,
)
def embed_claims(source_id: str, user_id: str, job_id: str) -> None:
    run_actor(_embed_claims(source_id, user_id, job_id))


async def _heal_embed_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    source_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "embed_claims", payload={"source_id": source_id}
        )
    embed_claims.send_with_options(
        args=(source_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_embed_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_embed_claims(original_message, stats))
