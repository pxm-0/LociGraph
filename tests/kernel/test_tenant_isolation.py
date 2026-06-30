import pytest
import sqlalchemy.exc

from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
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
