from __future__ import annotations

import os

import pytest

from kernel.db.jobs import JobRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_get_job_for_current_user(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        job = await JobRepository(conn).create(
            seeded_user, "ingest_source", payload={"source_id": "x"}
        )

    await _login(client)
    r = await client.get(f"/jobs/{job.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(job.id)
    assert body["job_type"] == "ingest_source"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_get_job_is_tenant_scoped(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        other_job = await JobRepository(conn).create(other_user, "ingest_source")

    await _login(client)
    r = await client.get(f"/jobs/{other_job.id}")

    assert r.status_code == 404
