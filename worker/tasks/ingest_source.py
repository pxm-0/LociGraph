from __future__ import annotations

import asyncio
from pathlib import Path

import dramatiq

from kernel.db.fragments import FragmentRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.ingestion.normalizer import Normalizer
from kernel.ingestion.registry import get_parser
from worker.broker import get_broker

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
            # Idempotency: skip if observations already exist for this source.
            if await ObservationRepository(conn).count_for_source(source_id) > 0:
                await SourceRepository(conn).mark_verified(source_id)
                await JobRepository(conn).mark_completed(job_id, result={"skipped": True})
                return

            fragments = get_parser(source.source_type).parse(Path(source.raw_storage_path or ""))
            await FragmentRepository(conn).bulk_insert(
                [f.to_fragment_row() for f in fragments], source_id, user_id
            )
            rows = Normalizer().normalize(fragments)
            await ObservationRepository(conn).bulk_insert(rows, source_id, user_id)
            await SourceRepository(conn).mark_verified(source_id)
            await JobRepository(conn).mark_completed(job_id, result={"observations": len(rows)})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=str(exc))
            await SourceRepository(conn).set_status(source_id, "FAILED")
        raise


@dramatiq.actor(queue_name="ingestion", max_retries=3)
def ingest_source(source_id: str, user_id: str, job_id: str) -> None:
    asyncio.run(_ingest(source_id, user_id, job_id))
