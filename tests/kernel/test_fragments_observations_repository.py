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


@pytest.mark.asyncio
async def test_filtered_list_by_source_and_speaker(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        src_a = await SourceRepository(conn).create(user_id, "json", "c-list-1")
        src_b = await SourceRepository(conn).create(user_id, "json", "c-list-2")
        await ObservationRepository(conn).bulk_insert(
            [
                {"content": "alpha", "speaker": "alice"},
                {"content": "beta", "speaker": "bob"},
            ],
            src_a.id,
            user_id,
        )
        await ObservationRepository(conn).bulk_insert(
            [{"content": "gamma", "speaker": "alice"}],
            src_b.id,
            user_id,
        )

        # unfiltered — all three rows
        all_obs = await ObservationRepository(conn).list()
        assert len(all_obs) >= 3  # noqa: PLR2004

        # filter by source_id
        src_a_obs = await ObservationRepository(conn).list(source_id=src_a.id)
        assert {o.content for o in src_a_obs} == {"alpha", "beta"}

        # filter by speaker
        alice_obs = await ObservationRepository(conn).list(speaker="alice")
        alice_contents = {o.content for o in alice_obs}
        assert {"alpha", "gamma"} <= alice_contents
        assert "beta" not in alice_contents

        # filter by source_id + speaker combined
        combo = await ObservationRepository(conn).list(
            source_id=src_a.id, speaker="alice"
        )
        assert len(combo) == 1
        assert combo[0].content == "alpha"

        # limit / offset
        paged = await ObservationRepository(conn).list(limit=2, offset=0)
        assert len(paged) == 2

        # count() mirrors list()'s filters
        assert await ObservationRepository(conn).count(source_id=src_a.id) == 2
        assert await ObservationRepository(conn).count(source_id=src_a.id, speaker="alice") == 1
        assert await ObservationRepository(conn).count(speaker="nobody") == 0
