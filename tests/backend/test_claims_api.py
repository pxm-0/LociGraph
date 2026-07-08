from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


@pytest.mark.asyncio
async def test_claims_and_candidates_list_for_current_user(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "claims-api-1")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha is useful."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Alpha is useful.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    claims = await client.get("/claims", params={"source_id": str(source.id)})
    candidates = await client.get("/concept-candidates", params={"source_id": str(source.id)})
    single = await client.get(f"/claims/{claim.id}")

    assert claims.status_code == 200
    assert claims.json()[0]["id"] == str(claim.id)
    assert candidates.status_code == 200
    assert candidates.json()[0]["candidate_name"] == "Alpha"
    assert single.status_code == 200
    assert single.json()["claim_text"] == "Alpha is useful."

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_claim_get_is_tenant_scoped(client, seeded_user, make_user):  # type: ignore[no-untyped-def]
    other_user = await make_user()
    async with session(other_user) as conn:
        source = await SourceRepository(conn).create(other_user, "json", "claims-api-2")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Hidden"}], source.id, other_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=other_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Hidden.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
    assert claim is not None

    await _login(client)
    assert (await client.get(f"/claims/{claim.id}")).status_code == 404
    assert (await client.get("/claims", params={"source_id": str(source.id)})).json() == []


@pytest.mark.asyncio
async def test_claims_count_reflects_total_not_just_the_page(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "claims-count-api")
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, seeded_user
        )
        for i, obs_id in enumerate(obs_ids):
            await ClaimRepository(conn).create(
                user_id=seeded_user,
                source_id=source.id,
                observation_id=obs_id,
                claim_text=f"Claim {i}.",
                claim_type="fact",
                assertion_type="reality",
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )

    await _login(client)
    r = await client.get(
        "/claims/count", params={"source_id": str(source.id)}
    )
    paged = await client.get(
        "/claims", params={"source_id": str(source.id), "limit": 1}
    )

    assert r.status_code == 200
    assert r.json() == {"total": 2}
    assert len(paged.json()) == 1  # the page is smaller than the real total

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_claims_filter_by_assertion_type(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(
            seeded_user, "json", "claims-assertion-filter-api"
        )
        obs_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": "one"}, {"content": "two"}], source.id, seeded_user
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_ids[0],
            claim_text="Fact claim.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=obs_ids[1],
            claim_text="Preference claim.",
            claim_type="preference",
            assertion_type="perception",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.get(
        "/claims", params={"source_id": str(source.id), "assertion_type": "perception"}
    )

    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["assertion_type"] == "perception"

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_approve_candidate_auto_enqueues_contradiction_detection_when_flag_set(
    client, seeded_user, monkeypatch
):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CONTRADICTION_AUTORUN", "true")
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "approve-autorun-on")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha is useful."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Alpha is useful.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r.status_code == 200
    assert len(sent) == 1
    sent_concept_id, sent_claim_id, sent_user_id, sent_job_id = sent[0]
    body = r.json()
    assert sent_concept_id == body["concept"]["id"]
    assert sent_claim_id == str(claim.id)
    assert sent_user_id == str(seeded_user)
    async with session(seeded_user) as conn:
        contradiction_jobs = await JobRepository(conn).list(job_type="detect_contradictions")
    assert len(contradiction_jobs) == 1
    assert sent_job_id == str(contradiction_jobs[0].id)

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))


@pytest.mark.asyncio
async def test_approve_candidate_does_not_enqueue_contradiction_detection_when_flag_unset(
    client, seeded_user, monkeypatch
):  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CONTRADICTION_AUTORUN", raising=False)
    sent: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "backend.app.api.claims.detect_contradictions.send",
        lambda *args: sent.append(args),
    )
    async with session(seeded_user) as conn:
        source = await SourceRepository(conn).create(seeded_user, "json", "approve-autorun-off")
        [observation_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Beta is useful."}], source.id, seeded_user
        )
        claim = await ClaimRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            observation_id=observation_id,
            claim_text="Beta is useful.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=seeded_user,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Beta",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    await _login(client)
    r = await client.post(f"/concept-candidates/{candidate.id}/approve")

    assert r.status_code == 200
    assert sent == []

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM claim_concept_edges"))
        await conn.execute(text("DELETE FROM concepts"))
        await conn.execute(text("DELETE FROM concept_candidates"))
        await conn.execute(text("DELETE FROM claims"))
        await conn.execute(text("DELETE FROM observations"))
        await conn.execute(text("DELETE FROM sources"))
