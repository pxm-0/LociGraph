from __future__ import annotations

import asyncio
import re
from itertools import batched
from typing import Any

import dramatiq

from kernel.ai.claim_extraction import ClaimExtractionSettings, get_claim_extractor
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.broker import get_broker
from worker.tasks.healing import HEAL_DELAY_MS, MAX_HEAL_GENERATIONS

get_broker()


def _public_error(message: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_*\\-]+", "sk-REDACTED", message)
    if "Incorrect API key provided" in redacted:
        return "OpenAI rejected the configured API key"
    return redacted


async def _extract_claims(
    source_id: str, user_id: str, job_id: str, force: bool = False
) -> None:
    settings = ClaimExtractionSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        # Defense in depth: the API already rejects a second extraction while
        # one is in flight, but a job enqueued before that guard existed (or
        # from a stale browser tab that didn't know about it) could still
        # land here — don't let it stomp on an already-running job's claims.
        other_job_id = await JobRepository(conn).find_active_job_for_source(
            "extract_claims", source_id, exclude_job_id=job_id
        )
        if other_job_id is not None:
            await JobRepository(conn).mark_completed(
                job_id, result={"skipped": f"duplicate of in-flight job {other_job_id}"}
            )
            return
        source = await SourceRepository(conn).get(source_id)
        if source is None:
            raise ValueError(f"source {source_id} not found")
        if source.import_status != "VERIFIED":
            raise ValueError(f"source {source_id} is not verified")
        claim_repo = ClaimRepository(conn)
        observations = await ObservationRepository(conn).list_for_source(source_id)
        if force:
            await claim_repo.delete_proposed_for_source(source_id)
            existing_observation_ids = set()
        else:
            existing_observation_ids = await claim_repo.observation_ids_with_live_claims(
                source_id
            )

    pending_observations = [
        obs for obs in observations if obs.id not in existing_observation_ids
    ]
    if not pending_observations:
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id,
                result={
                    "claims": 0,
                    "concept_candidates": 0,
                    "skipped_observations": len(observations),
                },
            )
        return

    async with session(user_id) as conn:
        await JobRepository(conn).update_progress(
            job_id, items_completed=0, items_total=len(pending_observations)
        )

    try:
        extractor = get_claim_extractor(settings)
        claim_count = 0
        candidate_count = 0
        processed_count = 0
        for batch in batched(pending_observations, settings.claim_extraction_batch_size):
            result = await extractor.extract(batch)
            async with session(user_id) as conn:
                claim_repo = ClaimRepository(conn)
                candidate_repo = ConceptCandidateRepository(conn)
                for extracted in result.claims:
                    claim = await claim_repo.create(
                        user_id=user_id,
                        source_id=source_id,
                        observation_id=extracted.observation_id,
                        claim_text=extracted.claim_text,
                        claim_type=extracted.claim_type,
                        confidence=extracted.confidence,
                        extraction_method=result.extraction_method,
                        model_name=result.model_name,
                        prompt_version=result.prompt_version,
                        metadata=extracted.metadata,
                    )
                    if claim is None:
                        continue
                    claim_count += 1
                    for candidate in extracted.concept_candidates:
                        await candidate_repo.create(
                            user_id=user_id,
                            source_id=source_id,
                            claim_id=claim.id,
                            candidate_name=candidate.candidate_name,
                            concept_type=candidate.concept_type,
                            rationale=candidate.rationale,
                            confidence=candidate.confidence,
                            extraction_method=result.extraction_method,
                            model_name=result.model_name,
                            prompt_version=result.prompt_version,
                            metadata=candidate.metadata,
                        )
                        candidate_count += 1

                processed_count += len(batch)
                await JobRepository(conn).update_progress(
                    job_id,
                    items_completed=processed_count,
                    items_total=len(pending_observations),
                )

        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id,
                result={
                    "claims": claim_count,
                    "concept_candidates": candidate_count,
                    "processed_observations": len(pending_observations),
                    "skipped_observations": len(observations)
                    - len(pending_observations),
                },
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=_public_error(str(exc)))
        raise


@dramatiq.actor(
    queue_name="extraction", max_retries=3, on_retry_exhausted="heal_extract_claims"
)
def extract_claims(
    source_id: str, user_id: str, job_id: str, force: bool = False
) -> None:
    asyncio.run(_extract_claims(source_id, user_id, job_id, force))


# Extraction is idempotent (already-claimed observations are skipped via
# existing_observation_ids), so once dramatiq's own retries for one job are
# exhausted, it's safe to just start a fresh job for the same source rather
# than leave it permanently failed. See worker/tasks/healing.py for the cap.
async def _heal_extract_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    source_id, user_id, _old_job_id, force = original_message["args"]
    heal_generation = original_message["options"].get("heal_generation", 0)
    if heal_generation >= MAX_HEAL_GENERATIONS:
        return
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": source_id, "force": force}
        )
    extract_claims.send_with_options(
        args=(source_id, user_id, str(new_job.id), force),
        delay=HEAL_DELAY_MS,
        heal_generation=heal_generation + 1,
    )


@dramatiq.actor(queue_name="extraction")
def heal_extract_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    asyncio.run(_heal_extract_claims(original_message, stats))
