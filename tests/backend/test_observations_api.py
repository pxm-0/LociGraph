from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_list_observations_for_current_user(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(str(seeded_user)) as conn:
        src = await SourceRepository(conn).create(str(seeded_user), "json", "obs-api-1")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "hello"}, {"content": "world"}], src.id, str(seeded_user)
        )
    await _login(client)
    r = await client.get("/observations")
    assert r.status_code == 200
    contents = {o["content"] for o in r.json()}
    assert {"hello", "world"} <= contents

    # cleanup via session(user_id) so RLS current_user_id is set
    async with session(str(seeded_user)) as conn:
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_observations_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/observations")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_observations_count_reflects_total_not_just_the_page(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(str(seeded_user)) as conn:
        src = await SourceRepository(conn).create(str(seeded_user), "json", "obs-count-api")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}, {"content": "three"}],
            src.id,
            str(seeded_user),
        )
    await _login(client)
    total = await client.get("/observations/count", params={"source_id": str(src.id)})
    paged = await client.get(
        "/observations", params={"source_id": str(src.id), "limit": 1}
    )

    assert total.status_code == 200
    assert total.json() == {"total": 3}
    assert len(paged.json()) == 1

    async with session(str(seeded_user)) as conn:
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))
