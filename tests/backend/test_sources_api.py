from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kernel.db.claims import ClaimRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.sources.submit_ingest",
        lambda *a, **k: calls.append(a),
    )
    return calls


@pytest.fixture
def _no_extraction_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.sources.submit_claim_extraction",
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
    assert all("claim_count" in item for item in items)
    assert all("claim_extraction_status" in item for item in items)

    get_r = await client.get(f"/sources/{source_id}")
    assert get_r.status_code == 200
    assert get_r.json()["id"] == source_id
    assert get_r.json()["observation_count"] == 0
    assert get_r.json()["claim_count"] == 0

    # cleanup (use session() so RLS current_user_id is set)
    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_get_unknown_source_returns_404(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/sources/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_manual_claim_extraction_creates_job(client, seeded_user, _no_extraction_broker):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "manual-extract")
        await SourceRepository(conn).mark_verified(source.id)

    await _login(client)
    r = await client.post(f"/sources/{source.id}/extract-claims")

    assert r.status_code == 202
    assert "job_id" in r.json()
    assert len(_no_extraction_broker) == 1

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_manual_claim_extraction_rejects_inaccessible_source(
    client, seeded_user, make_user, _no_extraction_broker  # type: ignore[no-untyped-def]
):
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "manual-other")
        await SourceRepository(conn).mark_verified(source.id)

    await _login(client)
    r = await client.post(f"/sources/{source.id}/extract-claims")

    assert r.status_code == 404
    assert _no_extraction_broker == []


@pytest.mark.asyncio
async def test_purge_zero_claim_source_returns_200_and_shows_purged(  # type: ignore[no-untyped-def]
    client, seeded_user, _no_broker
):
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("purge-me.json", b'[{"text":"purge"}]', "application/json")},
    )
    assert r.status_code == 202
    source_id = r.json()["source_id"]

    purge_r = await client.post(f"/sources/{source_id}/purge")
    assert purge_r.status_code == 200
    assert purge_r.json() == {"status": "purged"}

    get_r = await client.get(f"/sources/{source_id}")
    assert get_r.status_code == 200
    assert get_r.json()["import_status"] == "PURGED"

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_purge_source_with_claims_returns_409_and_unchanged(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "purge-with-claims")
        await SourceRepository(conn).mark_verified(source.id)
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "hi"}], source.id, seeded_user
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_ids[0],
            claim_text="a claim",
            claim_type="fact",
            confidence=0.9,
            extraction_method="manual",
            model_name=None,
            prompt_version=None,
        )

    await _login(client)
    purge_r = await client.post(f"/sources/{source.id}/purge")
    assert purge_r.status_code == 409
    assert purge_r.json()["detail"] == "source has claims — cannot delete after extraction"

    get_r = await client.get(f"/sources/{source.id}")
    assert get_r.status_code == 200
    assert get_r.json()["import_status"] == "VERIFIED"

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_purge_unknown_or_foreign_source_returns_404(
    client, seeded_user, make_user, _no_broker  # type: ignore[no-untyped-def]
):
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "purge-foreign")

    await _login(client)
    r = await client.post(f"/sources/{source.id}/purge")
    assert r.status_code == 404

    missing_r = await client.post("/sources/00000000-0000-0000-0000-000000000000/purge")
    assert missing_r.status_code == 404


@pytest.mark.asyncio
async def test_purge_removes_raw_file_from_disk(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/sources/upload",
        data={"source_type": "json"},
        files={"file": ("on-disk.json", b'[{"text":"disk"}]', "application/json")},
    )
    assert r.status_code == 202
    source_id = r.json()["source_id"]

    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).get(source_id)
    assert source is not None
    raw_path = Path(source.raw_storage_path)
    assert raw_path.exists()

    purge_r = await client.post(f"/sources/{source_id}/purge")
    assert purge_r.status_code == 200
    assert not raw_path.exists()

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM jobs"))
        await conn.execute(text("DELETE FROM sources"))
