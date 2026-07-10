from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.healing import MAX_HEAL_GENERATIONS
from worker.tasks.project_planetarium import _heal_project_planetarium, _project_planetarium, project_planetarium


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_one_concept(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "worker-test")
        await SourceRepository(conn).mark_verified(source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha matters."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Alpha matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
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
            user_id=user_id, claim_id=claim.id, embedding=_pad([1.0, 2.0]), model_name="fake"
        )
        job = await JobRepository(conn).create(user_id, "project_planetarium")
    return job


@pytest.mark.asyncio
async def test_project_planetarium_completes_and_reports_node_count(make_user):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    await _project_planetarium(str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
    assert done is not None
    assert done.status == "completed"
    assert done.result == {"node_count": 1}


@pytest.mark.asyncio
async def test_project_planetarium_records_failure_on_exception(make_user, monkeypatch):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    async def _boom(conn, user_id):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr("worker.tasks.project_planetarium.rebuild_planetarium", _boom)

    with pytest.raises(RuntimeError):
        await _project_planetarium(str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed = await JobRepository(conn).get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1


@pytest.mark.asyncio
async def test_heal_project_planetarium_creates_fresh_job_and_resends(make_user, monkeypatch):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    sent: dict = {}

    def _fake_send_with_options(*, args, delay, heal_generation):  # type: ignore[no-untyped-def]
        sent["args"] = args
        sent["delay"] = delay
        sent["heal_generation"] = heal_generation

    monkeypatch.setattr(
        "worker.tasks.project_planetarium.project_planetarium.send_with_options",
        _fake_send_with_options,
    )

    original_message = {"args": (str(user_id), str(job.id)), "options": {}}
    await _heal_project_planetarium(original_message, {})

    assert sent["heal_generation"] == 1
    assert sent["args"][0] == str(user_id)
    new_job_id = sent["args"][1]
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_project_planetarium_stops_at_generation_cap(make_user, monkeypatch):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.project_planetarium.project_planetarium.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_project_planetarium(original_message, {})

    assert calls == []


def test_project_planetarium_wired_to_heal_on_retry_exhausted():
    assert project_planetarium.options.get("on_retry_exhausted") == "heal_project_planetarium"
