import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository

EDGE_COUNT = 60  # > the repository's old accidental default of 50


@pytest.mark.asyncio
async def test_list_for_concept_with_no_limit_returns_all_rows(make_user):
    """Regression test: GET /concepts/{id}/claims (backend/app/api/concepts.py)
    calls list_for_concept with no limit argument and relies on the original
    unbounded behavior. Task 4 added a `limit: int = 50` default for
    kernel.planetarium's row cap, which silently truncated this unrelated
    endpoint. list_for_concept() with no limit must return every linked row."""
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "edge-repo-many")
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Popular Concept", concept_type="idea"
        )
        assert concept is not None

        observation_ids = await ObservationRepository(conn).bulk_insert(
            [{"content": f"Claim {i} about the popular concept."} for i in range(EDGE_COUNT)],
            source.id,
            user_id,
        )

        edge_repo = ClaimConceptEdgeRepository(conn)
        created_edge_ids = []
        for i, observation_id in enumerate(observation_ids):
            claim = await ClaimRepository(conn).create(
                user_id=user_id,
                source_id=source.id,
                observation_id=observation_id,
                claim_text=f"Claim {i} about the popular concept.",
                claim_type="fact",
                assertion_type="reality",
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            assert claim is not None
            candidate = await ConceptCandidateRepository(conn).create(
                user_id=user_id,
                source_id=source.id,
                claim_id=claim.id,
                candidate_name="Popular Concept",
                concept_type="idea",
                rationale=None,
                confidence=0.9,
                extraction_method="test",
                model_name=None,
                prompt_version=None,
            )
            edge = await edge_repo.create(
                user_id=user_id,
                claim_id=claim.id,
                concept_id=concept.id,
                concept_candidate_id=candidate.id,
                confidence=0.9,
            )
            assert edge is not None
            created_edge_ids.append(edge.id)

        edges = await edge_repo.list_for_concept(concept.id)

    assert len(edges) == EDGE_COUNT
    assert {e.id for e in edges} == set(created_edge_ids)
