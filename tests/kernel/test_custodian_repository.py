from __future__ import annotations

import pytest

from kernel.db.custodian import CustodianRepository
from kernel.db.session import session


@pytest.mark.asyncio
async def test_create_and_get_session_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        fetched = await repo.get_session(created.id)

    assert created.title is None
    assert created.ended_at is None
    assert fetched == created


@pytest.mark.asyncio
async def test_list_sessions_orders_newest_first(make_user):
    import asyncio

    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        first = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")

    await asyncio.sleep(0.01)  # Ensure different transaction timestamps

    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        second = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")

    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        listed = await repo.list_sessions()

    assert [s.id for s in listed] == [second.id, first.id]


@pytest.mark.asyncio
async def test_end_session_sets_ended_at_and_is_idempotent(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        ended = await repo.end_session(created.id)
        already_ended = await repo.end_session(created.id)

    assert ended is not None
    assert ended.ended_at is not None
    assert already_ended is None


@pytest.mark.asyncio
async def test_set_title_only_sets_when_null(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        created = await repo.create_session(user_id=user_id, model="gpt-4o-mini", provider="openai")
        await repo.set_title(created.id, "First title")
        await repo.set_title(created.id, "Second title")
        fetched = await repo.get_session(created.id)

    assert fetched is not None
    assert fetched.title == "First title"


@pytest.mark.asyncio
async def test_add_and_list_messages_in_order(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        custodian_session = await repo.create_session(
            user_id=user_id, model="gpt-4o-mini", provider="openai"
        )
        await repo.add_message(
            session_id=custodian_session.id, user_id=user_id, role="user", content="Hi there."
        )
        await repo.add_message(
            session_id=custodian_session.id,
            user_id=user_id,
            role="tool",
            content="",
            tool_name="search_archive",
            tool_input='{"query": "hi"}',
            tool_output="[]",
        )
        await repo.add_message(
            session_id=custodian_session.id, user_id=user_id, role="assistant", content="Hello!"
        )
        messages = await repo.list_messages(custodian_session.id)
        count = await repo.count_messages(custodian_session.id)

    assert [m.role for m in messages] == ["user", "tool", "assistant"]
    assert messages[1].tool_name == "search_archive"
    assert count == 3
