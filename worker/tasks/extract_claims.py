from __future__ import annotations

import logging
from itertools import batched
from typing import Any
from uuid import UUID

import dramatiq
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.ai.claim_extraction import ClaimExtractionSettings, get_claim_extractor
from kernel.ai.embeddings import EmbeddingSettings
from kernel.concepts_promotion import approve_candidate
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.broker import get_broker, run_actor
from worker.tasks.embed_claims import embed_claims
from worker.tasks.errors import public_error as _public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

logger = logging.getLogger(__name__)

get_broker()

# A single job working through tens of thousands of observations means one
# poisoned batch (or one crashed worker) stalls everything behind it, and a
# retry redoes the whole backlog. Splitting into fixed-size chunks bounds the
# blast radius of a failure to one chunk and lets independent chunks run
# concurrently instead of strictly one after another. Kept small (rather
# than e.g. 5000) so a bad chunk's blast radius and a healed retry's re-work
# both stay cheap even at the cost of creating more job rows.
MAX_OBSERVATIONS_PER_JOB = 1000


async def plan_claim_extraction_jobs(
    conn: AsyncConnection, source_id: str, user_id: str, force: bool = False
) -> list[tuple[UUID, list[str]]]:
    """Create one job per <=MAX_OBSERVATIONS_PER_JOB chunk of this source's
    pending observations. Returns (job_id, observation_ids) pairs to hand to
    dispatch_claim_extraction_jobs once this transaction has committed.

    force wipes existing proposed claims and reprocesses every observation;
    this must happen exactly once here, not per chunk, or concurrent chunks
    would race to delete each other's freshly-written claims.
    """
    claim_repo = ClaimRepository(conn)
    if force:
        await claim_repo.delete_proposed_for_source(source_id)
        observations = await ObservationRepository(conn).list_for_source(source_id)
        pending_ids = [str(obs.id) for obs in observations]
    else:
        observations = await ObservationRepository(conn).list_for_source(source_id)
        existing_observation_ids = await claim_repo.observation_ids_with_live_claims(source_id)
        pending_ids = [
            str(obs.id) for obs in observations if obs.id not in existing_observation_ids
        ]

    chunks = [
        pending_ids[i : i + MAX_OBSERVATIONS_PER_JOB]
        for i in range(0, len(pending_ids), MAX_OBSERVATIONS_PER_JOB)
    ] or [[]]  # still create one (no-op) job so a run with nothing pending shows up in history

    job_repo = JobRepository(conn)
    jobs: list[tuple[UUID, list[str]]] = []
    for chunk in chunks:
        job = await job_repo.create(
            user_id,
            "extract_claims",
            payload={"source_id": source_id, "force": force, "observation_ids": chunk},
        )
        jobs.append((job.id, chunk))
    return jobs


def dispatch_claim_extraction_jobs(
    jobs: list[tuple[UUID, list[str]]], source_id: str, user_id: str, force: bool
) -> None:
    """Send the dramatiq messages for jobs planned by plan_claim_extraction_jobs.

    Call only after the transaction that created those job rows has committed
    — sending first risks a worker picking up the message before the job row
    it needs (mark_running, etc.) is visible.
    """
    for job_id, observation_ids in jobs:
        extract_claims.send(source_id, user_id, str(job_id), force, observation_ids)


async def _extract_claims(
    source_id: str,
    user_id: str,
    job_id: str,
    force: bool = False,
    observation_ids: list[str] | None = None,
) -> None:
    settings = ClaimExtractionSettings.from_env()
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        if observation_ids is None:
            # Legacy path for messages enqueued before chunking existed (or a
            # heal of one): behaves exactly as extraction always did — work
            # out the source's full pending set right here. Chunked jobs
            # (observation_ids is not None) skip this: their sibling chunks
            # for the same source are expected, not duplicates, and force's
            # one-time delete already happened in plan_claim_extraction_jobs.
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
        all_observations = await ObservationRepository(conn).list_for_source(source_id)
        if observation_ids is None:
            if force:
                await claim_repo.delete_proposed_for_source(source_id)
                existing_observation_ids: set[UUID] = set()
            else:
                existing_observation_ids = await claim_repo.observation_ids_with_live_claims(
                    source_id
                )
            pending_observations = [
                obs for obs in all_observations if obs.id not in existing_observation_ids
            ]
        else:
            # Filter this chunk's assigned ids against claims already live —
            # keeps a heal/retry of this same chunk from redoing observations
            # a prior (crashed) attempt already got claims for.
            wanted_ids = {UUID(oid) for oid in observation_ids}
            existing_observation_ids = await claim_repo.observation_ids_with_live_claims(
                source_id
            )
            pending_observations = [
                obs
                for obs in all_observations
                if obs.id in wanted_ids and obs.id not in existing_observation_ids
            ]

    if not pending_observations:
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(
                job_id,
                result={
                    "claims": 0,
                    "concept_candidates": 0,
                    "skipped_observations": len(all_observations),
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
                        assertion_type=extracted.assertion_type,
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
                        created_candidate = await candidate_repo.create(
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
                        # Auto-promote: at this volume, requiring a human to
                        # click "approve" on every single candidate isn't
                        # viable, so a freshly extracted candidate goes
                        # straight to being a concept linked to its claim.
                        await approve_candidate(conn, created_candidate.id)

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
                    "skipped_observations": len(all_observations) - len(pending_observations),
                },
            )
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=_public_error(str(exc)))
        raise

    # Auto-enqueue embedding for this chunk's claims, deliberately OUTSIDE the
    # extraction try/except above and in its own try/except: a failure here
    # (malformed embedding env var, broker hiccup sending the message) must
    # never flip the already-completed extraction job back to failed, or
    # trigger a dramatiq retry that silently overwrites its real result
    # counts with a placeholder on re-completion. Sibling chunks for the same
    # source may also trigger this — claim_ids_without_vector makes each
    # embed_claims run a no-op once nothing is pending, so redundant triggers
    # are harmless rather than duplicating work.
    if claim_count > 0:
        try:
            if EmbeddingSettings.from_env().embedding_autorun:
                async with session(user_id) as conn:
                    embed_job = await JobRepository(conn).create(
                        user_id, "embed_claims", payload={"source_id": source_id}
                    )
                embed_claims.send(source_id, user_id, str(embed_job.id))
        except Exception as exc:
            logger.warning(
                "failed to auto-enqueue embed_claims for source %s: %s", source_id, exc
            )


# dramatiq's default 10-minute per-call time limit forcibly kills any single
# invocation still running past it — for a source with tens of thousands of
# observations (thousands of sequential batches, one OpenAI call each), that
# guarantees the job never finishes in one call. 3 hours lets a single
# invocation make real progress before needing to hand off via retry/heal.
EXTRACT_CLAIMS_TIME_LIMIT_MS = 3 * 60 * 60 * 1000


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_extract_claims",
    time_limit=EXTRACT_CLAIMS_TIME_LIMIT_MS,
)
def extract_claims(
    source_id: str,
    user_id: str,
    job_id: str,
    force: bool = False,
    observation_ids: list[str] | None = None,
) -> None:
    run_actor(_extract_claims(source_id, user_id, job_id, force, observation_ids))


# Extraction is idempotent (already-claimed observations are skipped via
# existing_observation_ids), so once dramatiq's own retries for one job are
# exhausted, it's safe to just start a fresh job for the same chunk rather
# than leave it permanently failed. See worker/tasks/healing.py for the cap.
async def _heal_extract_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    args = original_message["args"]
    # args[4] (observation_ids) is absent on messages enqueued before chunking
    # existed; None routes back through _extract_claims' legacy full-source path.
    source_id, user_id, _old_job_id, force = args[:4]
    observation_ids = args[4] if len(args) > 4 else None
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id,
            "extract_claims",
            payload={"source_id": source_id, "force": force, "observation_ids": observation_ids},
        )
    extract_claims.send_with_options(
        args=(source_id, user_id, str(new_job.id), force, observation_ids),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_extract_claims(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_extract_claims(original_message, stats))
