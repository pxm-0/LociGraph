from __future__ import annotations

from typing import Any

import dramatiq

from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.planetarium import rebuild_planetarium
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

get_broker()


async def _project_planetarium(user_id: str, job_id: str) -> None:
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
    try:
        async with session(user_id) as conn:
            nodes = await rebuild_planetarium(conn, user_id)
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(job_id, result={"node_count": len(nodes)})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


# A rebuild recomputes every concept's signals and re-runs UMAP over the
# whole archive — heavier than embedding one batch, but still bounded by a
# personal archive's concept count rather than an open-ended crawl.
PROJECT_PLANETARIUM_TIME_LIMIT_MS = 30 * 60 * 1000


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_project_planetarium",
    time_limit=PROJECT_PLANETARIUM_TIME_LIMIT_MS,
)
def project_planetarium(user_id: str, job_id: str) -> None:
    run_actor(_project_planetarium(user_id, job_id))


async def _heal_project_planetarium(
    original_message: dict[str, Any], stats: dict[str, Any]
) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(user_id, "project_planetarium")
    project_planetarium.send_with_options(
        args=(user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_project_planetarium(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_project_planetarium(original_message, stats))
