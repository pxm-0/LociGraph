from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.observations import ObservationRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.planetarium import rebuild_planetarium


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_concept(conn, user_id, name: str, seed: float):  # type: ignore[no-untyped-def]
    source = await SourceRepository(conn).create(user_id, "json", f"planetarium-{name}")
    await SourceRepository(conn).mark_verified(source.id)
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": f"{name} matters."}], source.id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source.id,
        observation_id=obs_id,
        claim_text=f"{name} matters.",
        claim_type="fact",
        assertion_type="reality",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    concept = await ConceptRepository(conn).create(
        user_id=user_id, concept_name=name, concept_type="entity"
    )
    candidate = await ConceptCandidateRepository(conn).create(
        user_id=user_id,
        source_id=source.id,
        claim_id=claim.id,
        candidate_name=name,
        concept_type="entity",
        rationale=None,
        confidence=0.9,
        extraction_method="test",
        model_name=None,
        prompt_version=None,
    )
    await ClaimConceptEdgeRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        concept_id=concept.id,
        concept_candidate_id=candidate.id,
        confidence=0.9,
    )
    await SemanticVectorRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        embedding=_pad([seed, seed * 2]),
        model_name="fake",
    )
    return concept, claim


@pytest.mark.asyncio
async def test_rebuild_planetarium_with_no_concepts_produces_no_nodes(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        nodes = await rebuild_planetarium(conn, user_id)
    assert nodes == []


@pytest.mark.asyncio
async def test_rebuild_planetarium_gives_higher_mass_to_more_active_concept(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        quiet_concept, _ = await _seed_concept(conn, user_id, "Quiet", 1.0)
        busy_concept, busy_claim = await _seed_concept(conn, user_id, "Busy", 2.0)

        # Give the busy concept extra revisions, an extra edge's worth of
        # contradiction, and an importance pin — the quiet concept gets none.
        await ImportanceSignalRepository(conn).create(
            user_id=user_id, target_type="concept", target_id=busy_concept.id
        )
        other_source = await SourceRepository(conn).create(user_id, "json", "planetarium-busy-2")
        await SourceRepository(conn).mark_verified(other_source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Busy conflicts."}], other_source.id, user_id
        )
        other_claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=other_source.id,
            observation_id=obs_id,
            claim_text="Busy conflicts.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert other_claim is not None
        await ContradictionRepository(conn).create(
            user_id=user_id,
            concept_id=busy_concept.id,
            claim_a_id=busy_claim.id,
            claim_b_id=other_claim.id,
            similarity=0.95,
            rationale="test contradiction",
        )

        nodes = await rebuild_planetarium(conn, user_id)
        node_by_concept = {n.concept_id: n for n in nodes}

    assert len(nodes) == 2
    assert node_by_concept[busy_concept.id].mass > node_by_concept[quiet_concept.id].mass


@pytest.mark.asyncio
async def test_rebuild_planetarium_replaces_rather_than_duplicates(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await _seed_concept(conn, user_id, "Alpha", 1.0)
        await rebuild_planetarium(conn, user_id)
        second = await rebuild_planetarium(conn, user_id)
        stored = await PlanetaryNodeRepository(conn).list_for_user(user_id)

    assert len(second) == 1
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_rebuild_planetarium_spreads_concepts_with_no_embeddings(make_user):
    # Concepts without an embedding used to all collapse onto (0,0,0), piling
    # every planet into one overlapping blob. They must instead spread out.
    user_id = await make_user()
    async with session(user_id) as conn:
        bare_a = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="BareA", concept_type="entity"
        )
        bare_b = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="BareB", concept_type="entity"
        )

        nodes = await rebuild_planetarium(conn, user_id)
        node_by_concept = {n.concept_id: n for n in nodes}

    assert len(nodes) == 2
    for concept in (bare_a, bare_b):
        node = node_by_concept[concept.id]
        assert (node.x, node.y, node.z) != (0.0, 0.0, 0.0)
    a, b = node_by_concept[bare_a.id], node_by_concept[bare_b.id]
    assert (a.x, a.y, a.z) != (b.x, b.y, b.z)


@pytest.mark.asyncio
async def test_rebuild_planetarium_query_count_does_not_scale_with_concept_count(make_user):
    # Regression test: rebuild_planetarium used to fetch revisions/edges/
    # contradictions/pins/vectors with one query PER CONCEPT (5*N round
    # trips) and insert nodes with one INSERT per node. Both are now bulk
    # operations, so the query count must stay flat as concept count grows
    # rather than scaling linearly with it.
    from sqlalchemy import event

    from kernel.db.engine import get_engine

    user_id = await make_user()
    async with session(user_id) as conn:
        for i in range(8):
            await _seed_concept(conn, user_id, f"Concept{i}", float(i))

        query_count = 0

        def _count(*_args: object, **_kwargs: object) -> None:
            nonlocal query_count
            query_count += 1

        engine = get_engine()
        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            nodes = await rebuild_planetarium(conn, user_id)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)

    assert len(nodes) == 8
    # 1 concept list + 5 bulk fetches + 1 delete + 1 insert batch = 8. The old
    # per-concept loop would have hit 5*8 + 8 + 2 = 50 for this fixture.
    assert query_count <= 12
