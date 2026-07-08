from __future__ import annotations

import pytest

from kernel.ai.contradiction_detection import ContradictionCheck
from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.detect_contradictions import (
    _detect_contradictions,
    _heal_detect_contradictions,
    detect_contradictions,
)
from worker.tasks.healing import MAX_HEAL_GENERATIONS


class FakeDetector:
    def __init__(self, is_contradiction: bool = True) -> None:
        self.is_contradiction = is_contradiction
        self.calls: list[tuple[str, str, str, str]] = []

    async def check(  # type: ignore[no-untyped-def]
        self, claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type
    ):
        self.calls.append(
            (claim_a_text, claim_a_assertion_type, claim_b_text, claim_b_assertion_type)
        )
        return ContradictionCheck(
            is_contradiction=self.is_contradiction, rationale="fake rationale"
        )


def _pad_vector(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_concept_with_two_linked_claims(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradiction-worker")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        claim_repo = ClaimRepository(conn)
        edge_repo = ClaimConceptEdgeRepository(conn)
        candidate_repo = ConceptCandidateRepository(conn)
        claims = []
        for text_ in ["It rained.", "It was sunny."]:
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
        vector_repo = SemanticVectorRepository(conn)
        await vector_repo.create(
            user_id=user_id,
            claim_id=claims[0].id,
            embedding=_pad_vector([1.0, 0.0]),
            model_name="test",
        )
        await vector_repo.create(
            user_id=user_id,
            claim_id=claims[1].id,
            embedding=_pad_vector([0.9, 0.1]),
            model_name="test",
        )
        job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": str(concept.id), "claim_id": str(claims[0].id)},
        )
    return concept, claims, job


@pytest.mark.asyncio
async def test_detect_contradictions_creates_a_row_when_llm_flags_a_pair(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    fake = FakeDetector(is_contradiction=True)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert len(rows) == 1
    assert done.status == "completed"
    assert done.result == {"contradictions_found": 1}
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_detect_contradictions_creates_nothing_when_llm_says_no_contradiction(
    make_user, monkeypatch
):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    fake = FakeDetector(is_contradiction=False)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
        done = await JobRepository(conn).get(job.id)

    assert rows == []
    assert done.result == {"contradictions_found": 0}


@pytest.mark.asyncio
async def test_detect_contradictions_skips_when_claim_has_no_embedding_yet(make_user, monkeypatch):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "contradiction-worker-2")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_id, concept_type="idea", concept_name="Test Concept", description=None
        )
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Unembedded claim."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Unembedded claim.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        job = await JobRepository(conn).create(
            user_id,
            "detect_contradictions",
            payload={"concept_id": str(concept.id), "claim_id": str(claim.id)},
        )
    fake = FakeDetector()
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claim.id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
    assert done.status == "completed"
    assert done.result == {"contradictions_found": 0, "skipped": "no_embedding_yet"}
    assert fake.calls == []


@pytest.mark.asyncio
async def test_detect_contradictions_filters_out_candidates_below_similarity_floor(
    make_user, monkeypatch
):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    monkeypatch.setenv("CONTRADICTION_SIMILARITY_FLOOR", "0.999")
    fake = FakeDetector(is_contradiction=True)
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.get_contradiction_detector", lambda settings: fake
    )

    await _detect_contradictions(str(concept.id), str(claims[0].id), str(user_id), str(job.id))

    async with session(user_id) as conn:
        rows = await ContradictionRepository(conn).list(concept_id=concept.id)
    assert rows == []
    assert fake.calls == []


def test_detect_contradictions_wired_to_heal_on_retry_exhausted():
    assert detect_contradictions.options.get("on_retry_exhausted") == "heal_detect_contradictions"


@pytest.mark.asyncio
async def test_heal_detect_contradictions_starts_a_fresh_job(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    sent: dict = {}
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.detect_contradictions.send_with_options",
        lambda **kwargs: sent.update(kwargs),
    )

    original_message = {
        "args": (str(concept.id), str(claims[0].id), str(user_id), str(job.id)),
        "options": {},
    }
    await _heal_detect_contradictions(original_message, {"retries": 3, "max_retries": 3})

    assert sent["heal_generation"] == 1
    new_concept_id, new_claim_id, new_user_id, new_job_id = sent["args"]
    assert new_concept_id == str(concept.id)
    assert new_claim_id == str(claims[0].id)
    assert new_user_id == str(user_id)
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_detect_contradictions_gives_up_after_max_generations(make_user, monkeypatch):
    user_id = await make_user()
    concept, claims, job = await _seed_concept_with_two_linked_claims(user_id)
    calls = []
    monkeypatch.setattr(
        "worker.tasks.detect_contradictions.detect_contradictions.send_with_options",
        lambda **kwargs: calls.append(kwargs),
    )

    original_message = {
        "args": (str(concept.id), str(claims[0].id), str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    await _heal_detect_contradictions(original_message, {"retries": 3, "max_retries": 3})

    assert calls == []
