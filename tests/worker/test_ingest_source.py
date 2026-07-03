import pytest

from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.healing import MAX_HEAL_GENERATIONS
from worker.tasks.ingest_source import _heal_ingest_source, _ingest, ingest_source


@pytest.mark.asyncio
async def test_ingest_failure_marks_source_failed_and_reraises(make_user, tmp_path):
    user_id = await make_user()
    missing = tmp_path / "does-not-exist.json"
    # deliberately NOT created so the parser raises FileNotFoundError

    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "e2e-fail", raw_storage_path=str(missing)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    with pytest.raises(FileNotFoundError):
        await _ingest(str(src.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed_src = await SourceRepository(conn).get(src.id)
        failed_job = await JobRepository(conn).get(job.id)

    assert failed_src.import_status == "FAILED"
    assert failed_job.status == "failed"
    assert failed_job.attempts >= 1


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
async def test_ingest_auto_enqueues_claim_extraction(make_user, tmp_path, monkeypatch):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('[{"text":"alpha"}]', encoding="utf-8")
    sent: list[tuple[object, ...]] = []
    monkeypatch.setenv("CLAIM_EXTRACTION_AUTORUN", "true")
    monkeypatch.setattr(
        "worker.tasks.ingest_source.extract_claims.send",
        lambda *args: sent.append(args),
    )

    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "e2e-auto-extract", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    await _ingest(str(src.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        jobs = await JobRepository(conn).count_by_statuses(["pending"])

    assert len(sent) == 1
    assert jobs >= 1


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


def test_ingest_source_wired_to_heal_on_retry_exhausted():
    assert ingest_source.options.get("on_retry_exhausted") == "heal_ingest_source"


@pytest.mark.asyncio
async def test_heal_ingest_source_starts_a_fresh_job(make_user, tmp_path, monkeypatch):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('["x"]', encoding="utf-8")
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "heal-me", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.ingest_source.ingest_source.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {"args": (str(src.id), str(user_id), str(job.id)), "options": {}}
    await _heal_ingest_source(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    assert sent["delay"] > 0
    new_source_id, new_user_id, new_job_id = sent["args"]
    assert new_source_id == str(src.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)

    async with session(user_id) as conn:
        new_job = await JobRepository(conn).get(new_job_id)
    assert new_job is not None
    assert new_job.job_type == "ingest_source"


@pytest.mark.asyncio
async def test_heal_ingest_source_gives_up_after_max_generations(make_user, tmp_path, monkeypatch):
    user_id = await make_user()
    raw = tmp_path / "s.json"
    raw.write_text('["x"]', encoding="utf-8")
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(
            user_id, "json", "heal-cap", raw_storage_path=str(raw)
        )
        job = await JobRepository(conn).create(user_id, "ingest_source")

    calls = []
    monkeypatch.setattr(
        "worker.tasks.ingest_source.ingest_source.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(src.id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_ingest_source(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
