from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.session import session


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.sources.submit_ingest",
        lambda *a, **k: calls.append(a),
    )
    return calls


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_upload_creates_pending_source_and_enqueues(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("a.json", b'[{"text":"hi"}]', "application/json")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "PENDING"
    assert "job_id" in body
    assert len(_no_broker) == 1  # enqueued exactly once
    # cleanup (use session() so RLS current_user_id is set)
    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_duplicate_checksum_returns_409(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    payload = {"data": {"source_type": "json"},
               "files": {"file": ("a.json", b'["x"]', "application/json")}}
    r1 = await client.post("/sources/upload", **payload)
    r2 = await client.post("/sources/upload", **payload)
    assert r1.status_code == 202
    assert r2.status_code == 409
    # cleanup (use session() so RLS current_user_id is set)
    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_bad_source_type_returns_400(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "bogus"},
        files={"file": ("a.json", b"[]", "application/json")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_auth(client, _no_broker):  # type: ignore[no-untyped-def]
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("a.json", b"[]", "application/json")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_and_get_sources_returns_only_current_user_rows(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("b.json", b'[{"text":"list-get"}]', "application/json")},
    )
    assert r.status_code == 202
    source_id = r.json()["source_id"]

    list_r = await client.get("/sources")
    assert list_r.status_code == 200
    items = list_r.json()
    assert any(item["id"] == source_id for item in items)
    assert all(item["import_status"] == "PENDING" for item in items if item["id"] == source_id)
    assert all("imported_at" in item for item in items)
    assert all("observation_count" in item for item in items)

    get_r = await client.get(f"/sources/{source_id}")
    assert get_r.status_code == 200
    assert get_r.json()["id"] == source_id
    assert get_r.json()["observation_count"] == 0

    # cleanup (use session() so RLS current_user_id is set)
    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_get_unknown_source_returns_404(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/sources/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
