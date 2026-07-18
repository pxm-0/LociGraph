from __future__ import annotations

import os

import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_dashboard_summary_reports_real_totals(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "dashboard-summary")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "hello"}], source.id, seeded_user
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Hello matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Hello", concept_type="idea"
        )

    await _login(client)
    r = await client.get("/dashboard/summary")

    assert r.status_code == 200
    body = r.json()
    assert body["source_count"] >= 1
    assert body["observation_count"] >= 1
    assert body["claim_count"] >= 1
    assert body["concept_count"] >= 1


@pytest.mark.asyncio
async def test_dashboard_summary_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/dashboard/summary")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_trends_zero_filled_window(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        await SourceRepository(conn).create(seeded_user, "json", "trends-src")

    await _login(client)
    r = await client.get("/dashboard/trends?window=7")

    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 7
    for entity in ("sources", "claims", "concepts", "contradictions"):
        points = body["series"][entity]
        assert len(points) == 7
        dates = [p["date"] for p in points]
        assert dates == sorted(dates)
        assert all(isinstance(p["count"], int) for p in points)
    assert body["series"]["sources"][-1]["count"] >= 1


@pytest.mark.asyncio
async def test_dashboard_trends_default_window(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/dashboard/trends")
    assert r.status_code == 200
    assert len(r.json()["series"]["claims"]) == 30


@pytest.mark.asyncio
async def test_dashboard_trends_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/dashboard/trends")
    assert r.status_code == 401
