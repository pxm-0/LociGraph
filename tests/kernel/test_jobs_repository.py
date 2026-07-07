import pytest
from sqlalchemy import text

from kernel.db.jobs import STALE_JOB_THRESHOLD_SECONDS, JobRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_job_lifecycle(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "ingest_source", payload={"source_id": "x"})
        assert job.status == "pending"

        await repo.mark_running(job.id)
        await repo.mark_completed(job.id, result={"observations": 5})
        done = await repo.get(job.id)
    assert done is not None
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_update_progress_round_trips(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "x"})
        assert job.items_completed is None
        assert job.items_total is None

        await repo.update_progress(job.id, items_completed=5, items_total=20)
        updated = await repo.get(job.id)
    assert updated is not None
    assert updated.items_completed == 5
    assert updated.items_total == 20


@pytest.mark.asyncio
async def test_record_attempt_increments_and_fails(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "ingest_source")
        await repo.record_attempt(job.id, error="boom")
        failed = await repo.get(job.id)
    assert failed is not None
    assert failed.attempts == 1
    assert failed.status == "failed"
    assert failed.error == "boom"


@pytest.mark.asyncio
async def test_find_active_job_for_source_finds_pending_or_running(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "src-1"})
        found = await repo.find_active_job_for_source("extract_claims", "src-1")
    assert found == job.id


@pytest.mark.asyncio
async def test_find_active_job_for_source_ignores_completed_and_failed(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        done = await repo.create(user_id, "extract_claims", payload={"source_id": "src-2"})
        await repo.mark_completed(done.id)
        failed = await repo.create(user_id, "extract_claims", payload={"source_id": "src-2"})
        await repo.record_attempt(failed.id, error="boom")
        found = await repo.find_active_job_for_source("extract_claims", "src-2")
    assert found is None


@pytest.mark.asyncio
async def test_find_active_job_for_source_excludes_given_job_id(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "src-3"})
        found = await repo.find_active_job_for_source(
            "extract_claims", "src-3", exclude_job_id=job.id
        )
    assert found is None


@pytest.mark.asyncio
async def test_find_active_job_for_source_scopes_by_job_type_and_source(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        await repo.create(user_id, "ingest_source", payload={"source_id": "src-4"})
        await repo.create(user_id, "extract_claims", payload={"source_id": "other-source"})
        found = await repo.find_active_job_for_source("extract_claims", "src-4")
    assert found is None


@pytest.mark.asyncio
async def test_mark_running_and_update_progress_set_heartbeat(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-1"})
        assert (await repo.get(job.id)).heartbeat_at is None

        await repo.mark_running(job.id)
        after_running = await repo.get(job.id)
        assert after_running.heartbeat_at is not None

        await repo.update_progress(job.id, items_completed=1, items_total=10)
        after_progress = await repo.get(job.id)
    assert after_progress.heartbeat_at is not None
    assert after_progress.heartbeat_at >= after_running.heartbeat_at


@pytest.mark.asyncio
async def test_find_active_job_for_source_reclaims_a_stale_running_job(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-2"})
        await repo.mark_running(job.id)
        # Simulate a worker that crashed a long time ago: backdate the heartbeat.
        await conn.execute(
            text(
                "UPDATE jobs SET heartbeat_at = now() - interval "
                f"'{STALE_JOB_THRESHOLD_SECONDS + 60} seconds' WHERE id = :id"
            ),
            {"id": str(job.id)},
        )

        found = await repo.find_active_job_for_source("extract_claims", "hb-2")
        reclaimed = await repo.get(job.id)

    assert found is None
    assert reclaimed.status == "failed"
    assert "auto-recovered" in reclaimed.error


@pytest.mark.asyncio
async def test_find_active_job_for_source_reclaims_a_legacy_job_with_no_heartbeat(make_user):
    # Jobs created before heartbeat_at existed (or any 'running' row a
    # heartbeat write somehow missed) have heartbeat_at = NULL forever;
    # heartbeat_at < ... never matches NULL, so staleness must fall back
    # to started_at for these.
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-4"})
        await repo.mark_running(job.id)
        await conn.execute(
            text(
                "UPDATE jobs SET heartbeat_at = NULL, started_at = now() - interval "
                f"'{STALE_JOB_THRESHOLD_SECONDS + 60} seconds' WHERE id = :id"
            ),
            {"id": str(job.id)},
        )

        found = await repo.find_active_job_for_source("extract_claims", "hb-4")
        reclaimed = await repo.get(job.id)

    assert found is None
    assert reclaimed.status == "failed"


@pytest.mark.asyncio
async def test_find_active_job_for_source_keeps_a_fresh_running_job(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-3"})
        await repo.mark_running(job.id)

        found = await repo.find_active_job_for_source("extract_claims", "hb-3")
        untouched = await repo.get(job.id)

    assert found == job.id
    assert untouched.status == "running"


@pytest.mark.asyncio
async def test_find_active_job_for_source_reclaims_a_stale_pending_job(make_user):
    # A job whose dramatiq message was lost or dead-lettered before any
    # worker picked it up never gets started_at/heartbeat_at, so staleness
    # for 'pending' rows must fall back to created_at.
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-5"})
        await conn.execute(
            text(
                "UPDATE jobs SET created_at = now() - interval "
                f"'{STALE_JOB_THRESHOLD_SECONDS + 60} seconds' WHERE id = :id"
            ),
            {"id": str(job.id)},
        )

        found = await repo.find_active_job_for_source("extract_claims", "hb-5")
        reclaimed = await repo.get(job.id)

    assert found is None
    assert reclaimed.status == "failed"
    assert "auto-recovered" in reclaimed.error


@pytest.mark.asyncio
async def test_find_active_job_for_source_keeps_a_fresh_pending_job(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        job = await repo.create(user_id, "extract_claims", payload={"source_id": "hb-6"})

        found = await repo.find_active_job_for_source("extract_claims", "hb-6")
        untouched = await repo.get(job.id)

    assert found == job.id
    assert untouched.status == "pending"


@pytest.mark.asyncio
async def test_list_filters_by_source_job_type_and_status(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        extract_job = await repo.create(
            user_id, "extract_claims", payload={"source_id": "list-src-1"}
        )
        await repo.mark_running(extract_job.id)
        embed_job = await repo.create(
            user_id, "embed_claims", payload={"source_id": "list-src-1"}
        )
        await repo.create(user_id, "extract_claims", payload={"source_id": "list-src-2"})

        for_source = await repo.list(source_id="list-src-1")
        by_type = await repo.list(source_id="list-src-1", job_type="embed_claims")
        by_status = await repo.list(source_id="list-src-1", status="running")
        other_source = await repo.list(source_id="list-src-2")

    assert {j.id for j in for_source} == {extract_job.id, embed_job.id}
    assert [j.id for j in by_type] == [embed_job.id]
    assert [j.id for j in by_status] == [extract_job.id]
    assert [j.source_id for j in for_source] == ["list-src-1", "list-src-1"]
    assert [j.id for j in other_source] != [extract_job.id, embed_job.id]


@pytest.mark.asyncio
async def test_list_orders_newest_first_and_respects_limit(make_user):
    # Two separate transactions so Postgres' now() (stable within one
    # transaction) actually differs between them, giving a real order.
    user_id = await make_user()
    async with session(user_id) as conn:
        first = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": "list-order"}
        )
    async with session(user_id) as conn:
        second = await JobRepository(conn).create(
            user_id, "extract_claims", payload={"source_id": "list-order"}
        )
    async with session(user_id) as conn:
        repo = JobRepository(conn)
        limited = await repo.list(source_id="list-order", limit=1)
        all_jobs = await repo.list(source_id="list-order")

    assert [j.id for j in limited] == [second.id]
    assert [j.id for j in all_jobs] == [second.id, first.id]
