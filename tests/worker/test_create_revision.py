from __future__ import annotations

import pytest

from kernel.ai.revision_synthesis import RevisionSynthesis
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.create_revision import (
    _create_revision,
    _heal_create_revision,
    create_revision,
)
from worker.tasks.healing import MAX_HEAL_GENERATIONS


class FakeSynthesizer:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def synthesize(
        self,
        previous_description,
        claim_a_text,
        claim_a_assertion_type,
        claim_b_text,
        claim_b_assertion_type,
    ):  # type: ignore[no-untyped-def]
        self.calls.append(
            (
                previous_description,
                claim_a_text,
                claim_a_assertion_type,
                claim_b_text,
                claim_b_assertion_type,
            )
        )
        return RevisionSynthesis(new_description="Synthesized text.", rationale="Fake rationale.")


async def _seed_contradiction(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "revision-worker")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description="Old."
        )
        claim_repo = ClaimRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claims = []
        for text_ in ["It rained.", "It was sunny, later than expected."]:
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": text_}], source.id, user_id
            )
            claim = await claim_repo.create(
                user_id=user_id,
                source_id=source.id,
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
                source_id=source.id,
                claim_id=claim.id,
                candidate_name="Test Concept",
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
            similarity=0.8,
            rationale="Detected rationale.",
        )
        assert contradiction is not None
        await ContradictionRepository(conn).classify(contradiction.id, "evolution")
        job = await JobRepository(conn).create(
            user_id, "create_revision", payload={"contradiction_id": str(contradiction.id)}
        )
    return concept, contradiction, job


@pytest.mark.asyncio
async def test_create_revision_synthesizes_and_updates_concept(make_user, monkeypatch):
    user_id = await make_user()
    concept, contradiction, job = await _seed_contradiction(user_id)
    fake = FakeSynthesizer()
    monkeypatch.setattr(
        "worker.tasks.create_revision.get_revision_synthesizer", lambda settings: fake
    )

    await _create_revision(str(contradiction.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        updated_concept = await ConceptRepository(conn).get(concept.id)
        revisions = await RevisionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert updated_concept.description == "Synthesized text."
    assert len(revisions) == 1
    assert revisions[0].source == "llm_synthesis"
    assert revisions[0].contradiction_id == contradiction.id
    assert revisions[0].previous_description == "Old."
    assert revisions[0].new_description == "Synthesized text."
    assert revisions[0].rationale == "Fake rationale."
    assert done.status == "completed"
    assert len(fake.calls) == 1


def test_create_revision_wired_to_heal_on_retry_exhausted():
    assert create_revision.options.get("on_retry_exhausted") == "heal_create_revision"


@pytest.mark.asyncio
async def test_heal_create_revision_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    _concept, contradiction, job = await _seed_contradiction(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.create_revision.create_revision.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(contradiction.id), str(user_id), str(job.id)),
        "options": {},
    }
    await _heal_create_revision(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    new_contradiction_id, new_user_id, new_job_id = sent["args"]
    assert new_contradiction_id == str(contradiction.id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_create_revision_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    _concept, contradiction, job = await _seed_contradiction(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.create_revision.create_revision.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(contradiction.id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_create_revision(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
