import pytest

from kernel.db.jobs import JobRepository
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
