from __future__ import annotations

from pathlib import Path
from typing import Any

import dramatiq

from kernel.ai.claim_extraction import ClaimExtractionSettings
from kernel.db.fragments import FragmentRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.ingestion.normalizer import Normalizer
from kernel.ingestion.registry import get_parser
from worker.broker import get_broker, run_actor
from worker.tasks.extract_claims import extract_claims
from worker.tasks.healing import HEAL_DELAY_MS, MAX_HEAL_GENERATIONS

get_broker()  # ensure a broker is set before the actor is declared


async def _ingest(source_id: str, user_id: str, job_id: str) -> None:
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
        await SourceRepository(conn).set_status(source_id, "INGESTING")

    try:
        async with session(user_id) as conn:
            source = await SourceRepository(conn).get(source_id)
            if source is None:
                raise ValueError(f"source {source_id} not found")
            if source.raw_storage_path is None:
                raise ValueError(f"source {source_id} has no raw_storage_path")
            # Idempotency: skip if observations already exist for this source.
            if await ObservationRepository(conn).count_for_source(source_id) > 0:
                await SourceRepository(conn).mark_verified(source_id)
                await JobRepository(conn).mark_completed(job_id, result={"skipped": True})
                return

            fragments = get_parser(source.source_type).parse(Path(source.raw_storage_path))
            await FragmentRepository(conn).bulk_insert(
                [f.to_fragment_row() for f in fragments], source_id, user_id
            )
            rows = Normalizer().normalize(fragments)
            await ObservationRepository(conn).bulk_insert(rows, source_id, user_id)
            await SourceRepository(conn).mark_verified(source_id)
            result: dict[str, Any] = {"observations": len(rows)}
            settings = ClaimExtractionSettings.from_env()
            if settings.claim_extraction_autorun and rows:
                extraction_job = await JobRepository(conn).create(
                    user_id,
                    "extract_claims",
                    payload={"source_id": str(source.id), "force": False},
                )
                extract_claims.send(
                    str(source.id), str(user_id), str(extraction_job.id), False
                )
                result["extract_claims_job_id"] = str(extraction_job.id)
            await JobRepository(conn).mark_completed(job_id, result=result)
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=str(exc))
            await SourceRepository(conn).set_status(source_id, "FAILED")
        raise


@dramatiq.actor(
    queue_name="ingestion", max_retries=3, on_retry_exhausted="heal_ingest_source"
)
def ingest_source(source_id: str, user_id: str, job_id: str) -> None:
    run_actor(_ingest(source_id, user_id, job_id))


# Ingestion is idempotent: fragments/observations/mark_verified all commit in
# a single transaction (kernel/db/session.py's session()), so a failed
# attempt rolls back atomically and a fresh retry safely re-parses from
# scratch. See worker/tasks/healing.py for the cap.
async def _heal_ingest_source(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    source_id, user_id, _old_job_id = original_message["args"]
    heal_generation = original_message["options"].get("heal_generation", 0)
    if heal_generation >= MAX_HEAL_GENERATIONS:
        return
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(
            user_id, "ingest_source", payload={"source_id": source_id}
        )
    ingest_source.send_with_options(
        args=(source_id, user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=heal_generation + 1,
    )


@dramatiq.actor(queue_name="ingestion")
def heal_ingest_source(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_ingest_source(original_message, stats))
