from __future__ import annotations

import os

import pytest

from kernel.db.jobs import JobRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.session import session


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):  # type: ignore[no-untyped-def]
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.planetarium.project_planetarium.send",
        lambda *a, **k: calls.append(a),
    )
    return calls


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


def _node(concept_id) -> dict:
    return {
        "concept_id": concept_id,
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
        "theta": 0.1,
        "phi": 0.2,
        "radius": 2.0,
        "mass": 0.5,
        "brightness": 0.9,
        "color": "#4a90d9",
        "visual_class": "planet",
        "projection_version": "v1/v1",
        "projection_algorithm": "umap",
    }


@pytest.mark.asyncio
async def test_rebuild_creates_job_and_enqueues(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post("/planetarium/rebuild")

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    async with session(seeded_user) as conn:
        job = await JobRepository(conn).get(body["job_id"])
    assert job is not None
    assert job.job_type == "project_planetarium"
    assert len(_no_broker) == 1


@pytest.mark.asyncio
async def test_rebuild_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.post("/planetarium/rebuild")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rebuild_has_no_duplicate_guard(client, seeded_user, _no_broker):  # type: ignore[no-untyped-def]
    await _login(client)
    first = await client.post("/planetarium/rebuild")
    second = await client.post("/planetarium/rebuild")

    assert first.json()["job_id"] != second.json()["job_id"]
    assert len(_no_broker) == 2


@pytest.mark.asyncio
async def test_list_nodes_empty_for_fresh_user(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/planetarium/nodes")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_nodes_returns_serialized_nodes(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["concept_id"] == str(concept.id)
    assert body[0]["visual_class"] == "planet"
    assert body[0]["mass"] == 0.5


@pytest.mark.asyncio
async def test_list_nodes_requires_auth(client):  # type: ignore[no-untyped-def]
    r = await client.get("/planetarium/nodes")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_nodes_isolated_between_tenants(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    other_user = await make_user()
    async with session(other_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=other_user, concept_name="Secret", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            other_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_nodes_includes_concept_name_and_type(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Epsilon", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get("/planetarium/nodes")

    assert r.status_code == 200
    body = r.json()
    assert body[0]["concept_name"] == "Epsilon"
    assert body[0]["concept_type"] == "entity"
