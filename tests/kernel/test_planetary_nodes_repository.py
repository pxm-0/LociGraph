from __future__ import annotations

import pytest

from kernel.db.concepts import ConceptRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.session import session


def _node(concept_id, *, visual_class="planet", mass=0.5) -> dict:
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
async def test_replace_all_for_user_inserts_and_replaces(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
        repo = PlanetaryNodeRepository(conn)

        first = await repo.replace_all_for_user(user_id, [_node(concept.id)])
        assert len(first) == 1
        assert first[0].concept_id == concept.id
        assert first[0].visual_class == "planet"

        second = await repo.replace_all_for_user(
            user_id, [_node(concept.id, visual_class="black_hole", mass=0.99)]
        )
        listed = await repo.list_for_user(user_id)

    assert len(second) == 1
    assert len(listed) == 1
    assert listed[0].visual_class == "black_hole"
    assert listed[0].mass == 0.99


@pytest.mark.asyncio
async def test_replace_all_for_user_can_clear_to_empty(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Beta", concept_type="entity"
        )
        assert concept is not None
        repo = PlanetaryNodeRepository(conn)
        await repo.replace_all_for_user(user_id, [_node(concept.id)])

        cleared = await repo.replace_all_for_user(user_id, [])
        listed = await repo.list_for_user(user_id)

    assert cleared == []
    assert listed == []
