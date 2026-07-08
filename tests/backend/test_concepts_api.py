from __future__ import annotations

import os

import pytest

from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


async def _make_candidate(conn, user_id, source_id, *, candidate_name="Careful Plans"):  # type: ignore[no-untyped-def]
    [observation_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": "The user cares about careful plans."}], source_id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        observation_id=observation_id,
        claim_text="The user cares about careful plans.",
        claim_type="preference",
        assertion_type="perception",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    assert claim is not None
    candidate = await ConceptCandidateRepository(conn).create(
        user_id=user_id,
        source_id=source_id,
        claim_id=claim.id,
        candidate_name=candidate_name,
        concept_type="idea",
        rationale="Preference topic",
        confidence=0.82,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    return claim, candidate


@pytest.mark.asyncio
async def test_approve_creates_concept_and_edge(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-1")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r.status_code == 200
    body = r.json()
    assert body["concept"]["concept_name"] == "Careful Plans"
    assert body["concept"]["claim_count"] == 1
    assert body["edge"]["concept_candidate_id"] == str(candidate.id)


@pytest.mark.asyncio
async def test_approve_is_idempotent(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-2")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)

    await _login(client)
    r1 = await client.post(f"/concept-candidates/{candidate.id}/approve")
    r2 = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["concept"]["id"] == r2.json()["concept"]["id"]
    assert r1.json()["edge"]["id"] == r2.json()["edge"]["id"]


@pytest.mark.asyncio
async def test_approve_missing_candidate_returns_404(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/concept-candidates/00000000-0000-0000-0000-000000000000/approve"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_approve_foreign_candidate_returns_404(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "concepts-api-3")
        _claim, candidate = await _make_candidate(conn, other_user, source.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_approve_non_proposed_candidate_returns_409(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-4")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)
        await ConceptCandidateRepository(conn).reject(candidate.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_reject_transitions_status(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-5")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/reject")

    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_missing_candidate_returns_404(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/concept-candidates/00000000-0000-0000-0000-000000000000/reject"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reject_foreign_candidate_returns_404(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "concepts-api-6")
        _claim, candidate = await _make_candidate(conn, other_user, source.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/reject")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reject_non_proposed_candidate_returns_409(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-7")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)
        await ConceptCandidateRepository(conn).reject(candidate.id)

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/reject")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_concepts_filters_by_type_and_status(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Alpha", concept_type="idea"
        )
        await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Beta", concept_type="entity"
        )

    await _login(client)
    r = await client.get("/concepts", params={"concept_type": "idea"})
    assert r.status_code == 200
    names = [c["concept_name"] for c in r.json()]
    assert "Alpha" in names
    assert "Beta" not in names

    r2 = await client.get("/concepts", params={"status": "active"})
    assert r2.status_code == 200
    assert len(r2.json()) >= 2


@pytest.mark.asyncio
async def test_concepts_count_reflects_total_not_just_the_page(client, seeded_user):  # type: ignore[no-untyped-def]
    # seeded_user accrues concepts across tests with no cleanup, so scope the
    # assertion to a concept_type unique to this test rather than the total.
    async with session(seeded_user) as conn:
        await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Zeta", concept_type="event"
        )
        await ConceptRepository(conn).create(
            user_id=seeded_user, concept_name="Eta", concept_type="event"
        )

    await _login(client)
    total = await client.get("/concepts/count", params={"concept_type": "event"})
    paged = await client.get("/concepts", params={"concept_type": "event", "limit": 1})

    assert total.status_code == 200
    assert total.json() == {"total": 2}
    assert len(paged.json()) == 1


@pytest.mark.asyncio
async def test_get_concept_returns_claim_count(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-8")
        _claim, candidate = await _make_candidate(conn, seeded_user, source.id)

    await _login(client)
    approve_r = await client.post(f"/concept-candidates/{candidate.id}/approve")
    concept_id = approve_r.json()["concept"]["id"]

    r = await client.get(f"/concepts/{concept_id}")
    assert r.status_code == 200
    assert r.json()["claim_count"] == 1


@pytest.mark.asyncio
async def test_get_unknown_concept_returns_404(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/concepts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_foreign_concept_returns_404(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=other_user, concept_name="Hidden Concept", concept_type="idea"
        )
    assert concept is not None

    await _login(client)
    r = await client.get(f"/concepts/{concept.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_concept_claims_returns_linked_claims(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "concepts-api-9")
        claim, candidate = await _make_candidate(conn, seeded_user, source.id)

    await _login(client)
    approve_r = await client.post(f"/concept-candidates/{candidate.id}/approve")
    concept_id = approve_r.json()["concept"]["id"]

    r = await client.get(f"/concepts/{concept_id}/claims")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == str(claim.id)


@pytest.mark.asyncio
async def test_list_concept_claims_unknown_concept_returns_404(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.get("/concepts/00000000-0000-0000-0000-000000000000/claims")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_concept_claims_foreign_concept_returns_404(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=other_user, concept_name="Hidden Concept 2", concept_type="idea"
        )
    assert concept is not None

    await _login(client)
    r = await client.get(f"/concepts/{concept.id}/claims")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_concept_endpoints_require_auth(client):  # type: ignore[no-untyped-def]
    assert (await client.get("/concepts")).status_code == 401
    assert (
        await client.get("/concepts/00000000-0000-0000-0000-000000000000")
    ).status_code == 401
    assert (
        await client.get("/concepts/00000000-0000-0000-0000-000000000000/claims")
    ).status_code == 401
    assert (
        await client.post(
            "/concept-candidates/00000000-0000-0000-0000-000000000000/approve"
        )
    ).status_code == 401
    assert (
        await client.post(
            "/concept-candidates/00000000-0000-0000-0000-000000000000/reject"
        )
    ).status_code == 401
