from __future__ import annotations

import pytest

from kernel.db.custodian import CustodianRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.session import session


async def _make_session(conn, user_id):  # type: ignore[no-untyped-def]
    return await CustodianRepository(conn).create_session(
        user_id=user_id, model="gpt-4o-mini", provider="openai"
    )


@pytest.mark.asyncio
async def test_create_and_get_round_trip(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id,
            session_id=custodian_session.id,
            item_type="note",
            content={"content": "Remember this."},
        )
        fetched = await repo.get(created.id)

    assert created.status == "proposed"
    assert created.target_id is None
    assert created.message_id is None
    assert fetched == created


@pytest.mark.asyncio
async def test_list_for_session_orders_oldest_first(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        first = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "first"},
        )
        second = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "second"},
        )
        listed = await repo.list_for_session(custodian_session.id)

    assert [i.id for i in listed] == [first.id, second.id]


@pytest.mark.asyncio
async def test_resolve_only_transitions_proposed_items(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "x"},
        )
        accepted = await repo.resolve(created.id, "accepted")
        already_resolved = await repo.resolve(created.id, "rejected")

    assert accepted is not None
    assert accepted.status == "accepted"
    assert accepted.resolved_at is not None
    assert already_resolved is None


@pytest.mark.asyncio
async def test_resolve_sets_target_id_when_given(make_user):
    from uuid import uuid4

    user_id = await make_user()
    new_id = uuid4()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="observation",
            content={"content": "x"},
        )
        resolved = await repo.resolve(created.id, "accepted", target_id=new_id)

    assert resolved is not None
    assert resolved.target_id == new_id


@pytest.mark.asyncio
async def test_set_message_id_backfills(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        custodian_session = await _make_session(conn, user_id)
        custodian_repo = CustodianRepository(conn)
        message = await custodian_repo.add_message(
            session_id=custodian_session.id,
            user_id=user_id,
            role="assistant",
            content="Test message",
        )
        repo = CustodianLoggedItemRepository(conn)
        created = await repo.create(
            user_id=user_id, session_id=custodian_session.id, item_type="note",
            content={"content": "x"},
        )
        await repo.set_message_id(created.id, message.id)
        fetched = await repo.get(created.id)

    assert fetched is not None
    assert fetched.message_id == message.id
