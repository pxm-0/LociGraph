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
