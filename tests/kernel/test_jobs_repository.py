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
