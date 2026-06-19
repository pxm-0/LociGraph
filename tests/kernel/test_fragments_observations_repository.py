import pytest

from kernel.db.fragments import FragmentRepository
from kernel.db.observations import ObservationRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


@pytest.mark.asyncio
async def test_bulk_insert_fragments_and_observations(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "chatgpt", "c-frag-1")

        frag_ids = await FragmentRepository(conn).bulk_insert(
            [
                {"raw_index": 0, "extracted_text": "hi", "author": "me"},
                {"raw_index": 1, "extracted_text": "there", "author": "you"},
            ],
            src.id,
            user_id,
        )
        assert len(frag_ids) == 2

        obs_ids = await ObservationRepository(conn).bulk_insert(
            [
                {"content": "hi", "speaker": "me", "fragment_id": frag_ids[0]},
                {"content": "there", "speaker": "you", "fragment_id": frag_ids[1]},
            ],
            src.id,
            user_id,
        )
        assert len(obs_ids) == 2

        count = await ObservationRepository(conn).count_for_source(src.id)
        observations = await ObservationRepository(conn).list_for_source(src.id)
    assert count == 2
    assert {o.content for o in observations} == {"hi", "there"}


@pytest.mark.asyncio
async def test_bulk_insert_empty_returns_empty(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "json", "c-frag-2")
        result = await FragmentRepository(conn).bulk_insert([], src.id, user_id)
    assert result == []


@pytest.mark.asyncio
async def test_bulk_insert_persists_confidence(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src = await SourceRepository(conn).create(user_id, "json", "c-conf-1")
        await ObservationRepository(conn).bulk_insert(
            [{"content": "x", "confidence": 0.5}], src.id, user_id
        )
        obs = await ObservationRepository(conn).list_for_source(src.id)
    assert obs[0].confidence == 0.5
