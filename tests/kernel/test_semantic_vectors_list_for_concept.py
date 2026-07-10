from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


@pytest.mark.asyncio
async def test_list_for_concept_returns_only_linked_vectors(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "planetarium-test")
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
        assert claim is not None
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
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

        linked = await SemanticVectorRepository(conn).list_for_concept(concept.id)
        other_concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Beta", concept_type="entity"
        )
        assert other_concept is not None
        unlinked = await SemanticVectorRepository(conn).list_for_concept(other_concept.id)

    assert len(linked) == 1
    assert linked[0].claim_id == claim.id
    assert unlinked == []
