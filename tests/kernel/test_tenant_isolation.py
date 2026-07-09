import pytest
import sqlalchemy.exc

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_user_b_cannot_read_user_a_sources(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src_a = await SourceRepository(conn).create(user_a, "markdown", "iso-a")

    # User B lists sources — must NOT see user A's row.
    async with session(user_b) as conn:
        b_sources = await SourceRepository(conn).list()
    assert all(s.id != src_a.id for s in b_sources)

    # User B fetches A's source by id — RLS hides it → None.
    async with session(user_b) as conn:
        leaked = await SourceRepository(conn).get(src_a.id)
    assert leaked is None

    # User B tries to purge A's source — RLS hides the row, no error, no-op.
    async with session(user_b) as conn:
        purged = await SourceRepository(conn).purge(src_a.id)
    assert purged is False

    async with session(user_a) as conn:
        still_there = await SourceRepository(conn).get(src_a.id)
    assert still_there is not None
    assert still_there.import_status != "PURGED"


@pytest.mark.asyncio
async def test_user_b_cannot_insert_rows_owned_by_user_a(make_user):
    user_a = await make_user()
    user_b = await make_user()

    # User B opens a session (context = B) but tries to insert a row tagged user_a.
    # WITH CHECK must reject it.
    async with session(user_b) as conn:
        with pytest.raises(sqlalchemy.exc.DBAPIError):
            await SourceRepository(conn).create(user_a, "json", "iso-cross")


@pytest.mark.asyncio
async def test_observations_isolated_between_tenants(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "pdf", "iso-obs")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "secret"}], src.id, user_a
        )

    async with session(user_b) as conn:
        b_view = await ObservationRepository(conn).list_for_source(src.id)
    assert b_view == []


@pytest.mark.asyncio
async def test_claims_and_concept_candidates_isolated_between_tenants(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-claims")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Secret claim source"}], src.id, user_a
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            observation_id=obs_id,
            claim_text="Secret claim.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        await ConceptCandidateRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            claim_id=claim.id,
            candidate_name="Secret",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )

    async with session(user_b) as conn:
        assert await ClaimRepository(conn).list(source_id=src.id) == []
        assert await ConceptCandidateRepository(conn).list(source_id=src.id) == []


@pytest.mark.asyncio
async def test_concepts_and_edges_isolated_between_tenants(make_user):
    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-concepts")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Secret concept source"}], src.id, user_a
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            observation_id=obs_id,
            claim_text="Secret claim about a concept.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            claim_id=claim.id,
            candidate_name="Secret Concept",
            concept_type="idea",
            rationale=None,
            confidence=0.8,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        concept = await ConceptRepository(conn).create(
            user_id=user_a,
            concept_name="Secret Concept",
            concept_type="idea",
        )
        assert concept is not None
        edge = await ClaimConceptEdgeRepository(conn).create(
            user_id=user_a,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.8,
        )
        assert edge is not None

    # User B cannot see user A's concepts or edges via list/get.
    async with session(user_b) as conn:
        assert await ConceptRepository(conn).list() == []
        assert await ConceptRepository(conn).get(concept.id) is None
        assert await ClaimConceptEdgeRepository(conn).list_for_claim(claim.id) == []
        assert await ClaimConceptEdgeRepository(conn).list_for_concept(concept.id) == []
        assert await ClaimConceptEdgeRepository(conn).get(edge.id) is None

    # User B cannot insert a concept or edge tagged as user A's.
    async with session(user_b) as conn:
        with pytest.raises(sqlalchemy.exc.DBAPIError):
            await ConceptRepository(conn).create(
                user_id=user_a,
                concept_name="Hostile Concept",
                concept_type="idea",
            )
    async with session(user_b) as conn:
        with pytest.raises(sqlalchemy.exc.DBAPIError):
            await ClaimConceptEdgeRepository(conn).create(
                user_id=user_a,
                claim_id=claim.id,
                concept_id=concept.id,
                concept_candidate_id=candidate.id,
                confidence=0.5,
            )


@pytest.mark.asyncio
async def test_semantic_vectors_isolated_between_tenants(make_user):
    from kernel.db.semantic_vectors import SemanticVectorRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-vectors")
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Secret vector source"}], src.id, user_a
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_a,
            source_id=src.id,
            observation_id=obs_id,
            claim_text="Secret claim for embedding.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        vector = await SemanticVectorRepository(conn).create(
            user_id=user_a,
            claim_id=claim.id,
            embedding=[0.1, 0.2] + [0.0] * 1534,
            model_name="test",
        )
        assert vector is not None

    async with session(user_b) as conn:
        assert await SemanticVectorRepository(conn).get_for_claim(claim.id) is None
        query_vec = [0.1, 0.2] + [0.0] * 1534
        assert await SemanticVectorRepository(conn).search_similar(query_vec) == []


@pytest.mark.asyncio
async def test_contradictions_isolated_between_tenants(make_user):
    from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
    from kernel.db.concept_candidates import ConceptCandidateRepository
    from kernel.db.concepts import ConceptRepository
    from kernel.db.contradictions import ContradictionRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        src = await SourceRepository(conn).create(user_a, "json", "iso-contradictions")
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_a, concept_type="idea", concept_name="Secret Concept", description=None
        )
        claims = []
        for text_ in ["Secret claim A.", "Secret claim B."]:
            [obs_id] = await ObservationRepository(conn).bulk_insert(
                [{"content": text_}], src.id, user_a
            )
            claim = await ClaimRepository(conn).create(
                user_id=user_a,
                source_id=src.id,
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
            candidate = await ConceptCandidateRepository(conn).create(
                user_id=user_a,
                source_id=src.id,
                claim_id=claim.id,
                candidate_name="Secret Concept",
                concept_type="idea",
                rationale=None,
                confidence=0.9,
                extraction_method="test",
                model_name="fake",
                prompt_version="v1",
            )
            await ClaimConceptEdgeRepository(conn).create(
                user_id=user_a,
                claim_id=claim.id,
                concept_id=concept.id,
                concept_candidate_id=candidate.id,
                confidence=0.9,
            )
            claims.append(claim)
        contradiction = await ContradictionRepository(conn).create(
            user_id=user_a,
            concept_id=concept.id,
            claim_a_id=claims[0].id,
            claim_b_id=claims[1].id,
            similarity=0.8,
            rationale="Secret rationale.",
        )
        assert contradiction is not None

    async with session(user_b) as conn:
        assert await ContradictionRepository(conn).list(concept_id=concept.id) == []
        assert await ContradictionRepository(conn).get(contradiction.id) is None


@pytest.mark.asyncio
async def test_revisions_isolated_between_tenants(make_user):
    from kernel.db.concepts import ConceptRepository
    from kernel.db.revisions import RevisionRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        concept = await ConceptRepository(conn).find_or_create(
            user_id=user_a, concept_type="idea", concept_name="Secret Concept", description=None
        )
        revision = await RevisionRepository(conn).create(
            user_id=user_a,
            concept_id=concept.id,
            contradiction_id=None,
            source="manual",
            previous_description=None,
            new_description="Secret revision.",
            rationale=None,
        )

    async with session(user_b) as conn:
        assert await RevisionRepository(conn).list(concept_id=concept.id) == []
        assert await RevisionRepository(conn).get(revision.id) is None


@pytest.mark.asyncio
async def test_custodian_isolated_between_tenants(make_user):
    from kernel.db.custodian import CustodianRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_a, model="gpt-4o-mini", provider="openai"
        )
        await CustodianRepository(conn).add_message(
            session_id=custodian_session.id,
            user_id=user_a,
            role="user",
            content="Secret question.",
        )

    async with session(user_b) as conn:
        assert await CustodianRepository(conn).get_session(custodian_session.id) is None
        assert await CustodianRepository(conn).list_sessions() == []


@pytest.mark.asyncio
async def test_custodian_logged_items_isolated_between_tenants(make_user):
    from kernel.db.custodian import CustodianRepository
    from kernel.db.custodian_logged_items import CustodianLoggedItemRepository

    user_a = await make_user()
    user_b = await make_user()

    async with session(user_a) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=user_a, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=user_a, session_id=custodian_session.id, item_type="note",
            content={"content": "Secret note."},
        )

    async with session(user_b) as conn:
        assert await CustodianLoggedItemRepository(conn).get(item.id) is None
        assert await CustodianLoggedItemRepository(conn).list_for_session(
            custodian_session.id
        ) == []
