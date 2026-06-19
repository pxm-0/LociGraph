import pytest
import sqlalchemy.exc

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
