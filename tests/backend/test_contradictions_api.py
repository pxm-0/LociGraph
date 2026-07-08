from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


async def _seed_contradiction(conn, user_id, source_id):  # type: ignore[no-untyped-def]
    concept = await ConceptRepository(conn).find_or_create(
        user_id=user_id, concept_type="idea", concept_name="Weather", description=None
    )
    claim_repo = ClaimRepository(conn)
    candidate_repo = ConceptCandidateRepository(conn)
    edge_repo = ClaimConceptEdgeRepository(conn)
    claims = []
    for text_ in ["It rained.", "It was sunny."]:
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": text_}], source_id, user_id
        )
        claim = await claim_repo.create(
            user_id=user_id,
            source_id=source_id,
            observation_id=obs_id,
            claim_text=text_,
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await candidate_repo.create(
            user_id=user_id,
            source_id=source_id,
            claim_id=claim.id,
            candidate_name="Weather",
            concept_type="idea",
            rationale=None,
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await edge_repo.create(
            user_id=user_id,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.9,
        )
        claims.append(claim)
    contradiction = await ContradictionRepository(conn).create(
        user_id=user_id,
        concept_id=concept.id,
        claim_a_id=claims[0].id,
        claim_b_id=claims[1].id,
        similarity=0.82,
        rationale="Both claims describe the same day's weather but disagree.",
    )
    assert contradiction is not None
    return concept, claims, contradiction


@pytest.mark.asyncio
async def test_list_contradictions_returns_both_claims_inline(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-1")
        concept, claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.get("/contradictions", params={"concept_id": str(concept.id)})

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == str(contradiction.id)
    assert body[0]["classification"] == "unresolved"
    assert {body[0]["claim_a"]["claim_text"], body[0]["claim_b"]["claim_text"]} == {
        "It rained.",
        "It was sunny.",
    }

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_contradictions_count_and_filter_by_classification(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-2")
        concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    before = await client.get(
        "/contradictions/count",
        params={"concept_id": str(concept.id), "classification": "unresolved"},
    )
    empty = await client.get(
        "/contradictions", params={"concept_id": str(concept.id), "classification": "evolution"}
    )

    assert before.json() == {"total": 1}
    assert empty.json() == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_updates_it(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-3")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "evolution"}
    )

    assert r.status_code == 200
    body = r.json()
    assert body["classification"] == "evolution"
    assert body["classified_at"] is not None

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_rejects_invalid_classification(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "contradictions-api-4")
        _concept, _claims, contradiction = await _seed_contradiction(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(
        f"/contradictions/{contradiction.id}/classify", json={"classification": "not-a-real-value"}
    )

    assert r.status_code == 422

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM contradictions"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_classify_contradiction_404s_when_not_found(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/contradictions/00000000-0000-0000-0000-000000000000/classify",
        json={"classification": "evolution"},
    )
    assert r.status_code == 404
