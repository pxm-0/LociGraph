from __future__ import annotations

import logging
from typing import Any

import dramatiq

from kernel.ai.revision_synthesis import RevisionSynthesisSettings, get_revision_synthesizer
from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

logger = logging.getLogger(__name__)

get_broker()


async def _create_revision(contradiction_id: str, user_id: str, job_id: str) -> None:
    settings = RevisionSynthesisSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        contradiction = await ContradictionRepository(conn).get(contradiction_id)
        if contradiction is None:
            raise ValueError(f"contradiction {contradiction_id} not found")
        concept = await ConceptRepository(conn).get(contradiction.concept_id)
        if concept is None:
            raise ValueError(f"concept {contradiction.concept_id} not found")
        claim_a = await ClaimRepository(conn).get(contradiction.claim_a_id)
        claim_b = await ClaimRepository(conn).get(contradiction.claim_b_id)
        if claim_a is None or claim_b is None:
            raise ValueError(f"claims for contradiction {contradiction_id} not found")

    try:
        synthesizer = get_revision_synthesizer(settings)
        synthesis = await synthesizer.synthesize(
            concept.description,
            claim_a.claim_text,
            claim_a.assertion_type,
            claim_b.claim_text,
            claim_b.assertion_type,
        )
        async with session(user_id) as conn:
            await ConceptRepository(conn).update_description(
                concept.id, synthesis.new_description
            )
            await RevisionRepository(conn).create(
                user_id=user_id,
                concept_id=concept.id,
                contradiction_id=contradiction.id,
                source="llm_synthesis",
                previous_description=concept.description,
                new_description=synthesis.new_description,
                rationale=synthesis.rationale,
            )
            await JobRepository(conn).mark_completed(job_id, result={"revised": True})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_create_revision",
)
def create_revision(contradiction_id: str, user_id: str, job_id: str) -> None:
    run_actor(_create_revision(contradiction_id, user_id, job_id))


async def _heal_create_revision(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    contradiction_id, user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "create_revision", payload={"contradiction_id": contradiction_id}
        )
    create_revision.send_with_options(
        args=(contradiction_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_create_revision(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_create_revision(original_message, stats))
