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


def _node(concept_id, visual_class: str = "planet", mass: float = 0.5) -> dict:
    return {
        "concept_id": concept_id,
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
        "theta": 0.1,
        "phi": 0.2,
        "radius": 2.0,
        "mass": mass,
        "brightness": 0.9,
        "color": "#4a90d9",
        "visual_class": visual_class,
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


@pytest.mark.asyncio
async def test_node_detail_returns_breakdown_for_embedded_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.claims import ClaimRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.concepts import ConceptRepository
    from kernel.db.observations import ObservationRepository
    from kernel.db.semantic_vectors import SemanticVectorRepository
    from kernel.db.sources import SourceRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Zeta", concept_type="entity"
        )
        assert concept is not None
        source = await SourceRepository(conn).create(seeded_user, "json", "detail-test")
        await SourceRepository(conn).mark_verified(source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Zeta matters."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Zeta matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Zeta",
            concept_type="entity",
            rationale=None,
            confidence=0.9,
            extraction_method="test",
            model_name=None,
            prompt_version=None,
        )
        await ClaimConceptEdgeRepository(conn).create(
            user_id=seeded_user,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.9,
        )
        await SemanticVectorRepository(conn).create(
            user_id=seeded_user,
            claim_id=claim.id,
            embedding=[0.1] * 1536,
            model_name="fake",
        )
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id, visual_class="black_hole", mass=0.9)]
        )

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")

    assert r.status_code == 200
    body = r.json()
    assert body["concept_name"] == "Zeta"
    assert body["visual_class"] == "black_hole"
    assert body["edge_count"] == 1
    assert body["revision_count"] == 0
    assert body["contradiction_count"] == 0
    assert body["pin_count"] == 0
    assert body["is_embedded"] is True


@pytest.mark.asyncio
async def test_node_detail_flags_non_embedded_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Eta", concept_type="entity"
        )
        assert concept is not None
        await PlanetaryNodeRepository(conn).replace_all_for_user(
            seeded_user, [_node(concept.id)]
        )

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")

    assert r.status_code == 200
    assert r.json()["is_embedded"] is False


@pytest.mark.asyncio
async def test_node_detail_404s_for_unknown_concept(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/planetarium/nodes/00000000-0000-0000-0000-000000000000/detail")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_node_detail_404s_when_concept_has_no_planetarium_data(client, seeded_user):  # type: ignore[no-untyped-def]
    from kernel.db.concepts import ConceptRepository

    async with session(seeded_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Theta", concept_type="entity"
        )
        assert concept is not None

    await _login(client)
    r = await client.get(f"/planetarium/nodes/{concept.id}/detail")
    assert r.status_code == 404
