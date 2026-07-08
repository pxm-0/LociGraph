from __future__ import annotations

import logging
from typing import Any

import dramatiq

from kernel.ai.contradiction_detection import ContradictionSettings, get_contradiction_detector
from kernel.db.claims import ClaimRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

logger = logging.getLogger(__name__)

get_broker()


async def _detect_contradictions(
    concept_id: str, claim_id: str, user_id: str, job_id: str
) -> None:
    settings = ContradictionSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        vector = await SemanticVectorRepository(conn).get_for_claim(claim_id)
        if vector is None:
            await JobRepository(conn).mark_completed(
                job_id, result={"contradictions_found": 0, "skipped": "no_embedding_yet"}
            )
            return
        candidates = await SemanticVectorRepository(conn).search_similar_within_concept(
            concept_id=concept_id,
            exclude_claim_id=claim_id,
            query_embedding=vector.embedding,
            limit=settings.contradiction_candidate_limit,
        )
        claim = await ClaimRepository(conn).get(claim_id)
        if claim is None:
            raise ValueError(f"claim {claim_id} not found")

    try:
        found = 0
        detector = get_contradiction_detector(settings)
        for candidate in candidates:
            if candidate.similarity < settings.contradiction_similarity_floor:
                continue
            check = await detector.check(
                claim.claim_text,
                claim.assertion_type,
                candidate.claim.claim_text,
                candidate.claim.assertion_type,
            )
            if not check.is_contradiction:
                continue
            async with session(user_id) as conn:
                created = await ContradictionRepository(conn).create(
                    user_id=user_id,
                    concept_id=concept_id,
                    claim_a_id=claim_id,
                    claim_b_id=str(candidate.claim.id),
                    similarity=candidate.similarity,
                    rationale=check.rationale,
                )
                if created is not None:
                    found += 1

        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id, result={"contradictions_found": found}
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_detect_contradictions",
)
def detect_contradictions(concept_id: str, claim_id: str, user_id: str, job_id: str) -> None:
    run_actor(_detect_contradictions(concept_id, claim_id, user_id, job_id))


async def _heal_detect_contradictions(
    original_message: dict[str, Any], stats: dict[str, Any]
) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    concept_id, claim_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": concept_id, "claim_id": claim_id},
        )
    detect_contradictions.send_with_options(
        args=(concept_id, claim_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_detect_contradictions(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_detect_contradictions(original_message, stats))
