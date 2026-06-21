import pytest

from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.ingest_source import _ingest


@pytest.mark.asyncio
async def test_ingest_parses_and_persists_observations(make_user, tmp_path):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('[{"text":"alpha"},{"text":"beta"}]', encoding="utf-8")

    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "e2e-1", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    await _ingest(str(src.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        refreshed = await SourceRepository(conn).get(src.id)
        count = await ObservationRepository(conn).count_for_source(src.id)
        done = await JobRepository(conn).get(job.id)
    assert refreshed.import_status == "VERIFIED"
    assert count == 2
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_ingest_is_idempotent(make_user, tmp_path):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('["x"]', encoding="utf-8")
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "e2e-2", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")
    await _ingest(str(src.id), str(user_id), str(job.id))
    await _ingest(str(src.id), str(user_id), str(job.id))  # second run must not double-insert
    async with session(user_id) as conn:
        count = await ObservationRepository(conn).count_for_source(src.id)
    assert count == 1
