from __future__ import annotations

import os

import pytest

from kernel.db.jobs import JobRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_get_job_returns_serialized_job(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        job = await JobRepository(conn).create(
            seeded_user, "extract_claims", payload={"source_id": "job-api-1"}
        )

    await _login(client)
    r = await client.get(f"/jobs/{job.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(job.id)
    assert body["job_type"] == "extract_claims"
    assert body["status"] == "pending"
    assert body["source_id"] == "job-api-1"


@pytest.mark.asyncio
async def test_get_unknown_job_returns_404(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_filters_by_source_and_type(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        repo = JobRepository(conn)
        extract_job = await repo.create(
            seeded_user, "extract_claims", payload={"source_id": "job-api-list-1"}
        )
        embed_job = await repo.create(
            seeded_user, "embed_claims", payload={"source_id": "job-api-list-1"}
        )
        await repo.create(seeded_user, "extract_claims", payload={"source_id": "job-api-list-2"})

    await _login(client)
    for_source = await client.get("/jobs", params={"source_id": "job-api-list-1"})
    by_type = await client.get(
        "/jobs", params={"source_id": "job-api-list-1", "job_type": "embed_claims"}
    )

    assert for_source.status_code == 200
    ids = {j["id"] for j in for_source.json()}
    assert ids == {str(extract_job.id), str(embed_job.id)}

    assert by_type.status_code == 200
    assert [j["id"] for j in by_type.json()] == [str(embed_job.id)]


@pytest.mark.asyncio
async def test_list_jobs_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/jobs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_jobs_is_tenant_scoped(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        await JobRepository(conn).create(
            other_user, "extract_claims", payload={"source_id": "job-api-foreign"}
        )

    await _login(client)
    r = await client.get("/jobs", params={"source_id": "job-api-foreign"})

    assert r.status_code == 200
    assert r.json() == []
