from __future__ import annotations

import os

import pytest

from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_dashboard_summary_counts_current_user_rows(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(
            seeded_user, "markdown", "dashboard-source", original_filename="daily.md"
        )
        await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, seeded_user
        )
        jobs = JobRepository(conn)
        await jobs.create(seeded_user, "ingest_source")
        running = await jobs.create(seeded_user, "ingest_source")
        completed = await jobs.create(seeded_user, "ingest_source")
        await jobs.mark_running(running.id)
        await jobs.mark_completed(completed.id)

    await _login(client)
    r = await client.get("/dashboard/summary")

    assert r.status_code == 200
    body = r.json()
    assert body["source_count"] >= 1
    assert body["observation_count"] >= 2
    assert body["pending_job_count"] >= 2
    recent = body["recent_sources"]
    assert any(item["id"] == str(source.id) for item in recent)
    assert any(item["observation_count"] == 2 for item in recent)
