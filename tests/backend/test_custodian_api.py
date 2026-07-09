from __future__ import annotations

import asyncio
import json
import os

import pytest
from sqlalchemy import text

from kernel.ai.custodian import CustodianReply, ToolCallRecord
from kernel.db.custodian import CustodianRepository
from kernel.db.custodian_logged_items import CustodianLoggedItemRepository
from kernel.db.session import session


async def _login(client):  # type: ignore[no-untyped-def]
    await client.post("/auth/login", json={"password": os.environ["LOCIGRAPH_PASSWORD"]})


class FakeCustodian:
    def __init__(self, reply: CustodianReply) -> None:
        self._reply = reply

    async def reply(self, conn, user_id, session_id, history, on_token, on_tool_call):  # type: ignore[no-untyped-def]
        for chunk in self._reply.content.split(" "):
            await on_token(chunk + " ")
        for call in self._reply.tool_calls:
            await on_tool_call(call)
        return self._reply


async def _drain_sse(response) -> list[tuple[str, dict]]:  # type: ignore[no-untyped-def]
    events = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            lines = raw.split("\n")
            event = next(l[len("event: "):] for l in lines if l.startswith("event: "))
            data = json.loads(next(l[len("data: "):] for l in lines if l.startswith("data: ")))
            events.append((event, data))
    return events


@pytest.mark.asyncio
async def test_create_and_list_sessions(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    listed = await client.get("/custodian/sessions")

    assert created.status_code == 200
    assert created.json()["title"] is None
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == created.json()["id"]

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_send_message_streams_tokens_and_persists_reply(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    fake = FakeCustodian(
        CustodianReply(
            content="Hello there.",
            tool_calls=[
                ToolCallRecord(
                    tool_name="search_archive",
                    tool_input=json.dumps({"query": "hi", "limit": 5}),
                    tool_output="[]",
                )
            ],
        )
    )
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    session_id = created.json()["id"]

    async with client.stream(
        "POST", f"/custodian/sessions/{session_id}/messages", json={"content": "Hi"}
    ) as response:
        events = await _drain_sse(response)

    assert ("done", {}) in events
    assert any(e == "tool_call" and d["tool_name"] == "search_archive" for e, d in events)
    assert any(e == "token" for e, _ in events)

    async with session(seeded_user) as conn:
        messages = await CustodianRepository(conn).list_messages(session_id)
    roles = [m.role for m in messages]
    assert roles == ["user", "tool", "assistant"]
    assert messages[0].content == "Hi"
    assert messages[2].content == "Hello there."

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_send_message_404s_for_unknown_session(client, seeded_user):  # type: ignore[no-untyped-def]
    await _login(client)
    r = await client.post(
        "/custodian/sessions/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "Hi"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_send_message_409s_once_message_cap_is_hit(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    monkeypatch.setenv("CUSTODIAN_MAX_MESSAGES_PER_SESSION", "1")
    fake = FakeCustodian(CustodianReply(content="ok", tool_calls=[]))
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    created = await client.post("/custodian/sessions", json={})
    session_id = created.json()["id"]

    async with client.stream(
        "POST", f"/custodian/sessions/{session_id}/messages", json={"content": "Hi"}
    ) as first:
        await _drain_sse(first)

    second = await client.post(
        f"/custodian/sessions/{session_id}/messages", json={"content": "Again"}
    )

    assert second.status_code == 409

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


class FakeCustodianWithProposal:
    def __init__(self, proposal_tool_output: str) -> None:
        self._proposal_tool_output = proposal_tool_output

    async def reply(self, conn, user_id, session_id, history, on_token, on_tool_call):  # type: ignore[no-untyped-def]
        await on_token("Sure, I've proposed that.")
        record = ToolCallRecord(
            tool_name="propose_note",
            tool_input=json.dumps({"content": "Remember this."}),
            tool_output=self._proposal_tool_output,
        )
        await on_tool_call(record)
        return CustodianReply(content="Sure, I've proposed that.", tool_calls=[record])


@pytest.mark.asyncio
async def test_message_id_is_backfilled_onto_the_logged_item(  # type: ignore[no-untyped-def]
    client, seeded_user, monkeypatch
):
    async with session(seeded_user) as conn:
        from kernel.db.custodian import CustodianRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Remember this."},
        )
    fake = FakeCustodianWithProposal(json.dumps({"proposal_id": str(item.id), "status": "proposed"}))
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    await _login(client)
    async with client.stream(
        "POST", f"/custodian/sessions/{custodian_session.id}/messages", json={"content": "log it"}
    ) as response:
        await _drain_sse(response)

    async with session(seeded_user) as conn:
        backfilled = await CustodianLoggedItemRepository(conn).get(item.id)

    assert backfilled is not None
    assert backfilled.message_id is not None

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_accept_and_reject_endpoints(client, seeded_user):  # type: ignore[no-untyped-def]
    async with session(seeded_user) as conn:
        from kernel.db.custodian import CustodianRepository

        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        note_item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Accept me."},
        )
        reject_item = await CustodianLoggedItemRepository(conn).create(
            user_id=seeded_user, session_id=custodian_session.id, item_type="note",
            content={"content": "Reject me."},
        )

    await _login(client)
    listed = await client.get(f"/custodian/sessions/{custodian_session.id}/logged-items")
    accepted = await client.post(f"/custodian/logged-items/{note_item.id}/accept")
    rejected = await client.post(f"/custodian/logged-items/{reject_item.id}/reject")
    accept_again = await client.post(f"/custodian/logged-items/{note_item.id}/accept")

    assert len(listed.json()) == 2
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert accept_again.status_code == 409

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM notes"))
        await conn.execute(text("DELETE FROM custodian_logged_items"))
        await conn.execute(text("DELETE FROM custodian_sessions"))


@pytest.mark.asyncio
async def test_generate_and_persist_completes_even_when_nothing_drains_the_queue(  # type: ignore[no-untyped-def]
    seeded_user, monkeypatch
):
    # _generate_and_persist is a detached asyncio.Task (see _spawn in
    # backend/app/api/custodian.py) — in production, a client disconnecting
    # mid-stream means nothing ever reads from its output queue again. This
    # test reproduces exactly that: it calls _generate_and_persist directly
    # and never touches the queue it writes to, proving completion doesn't
    # depend on a consumer. (An httpx.ASGITransport-based HTTP-layer version
    # of this test cannot work — that transport fully drains the SSE
    # response before the client sees any bytes, so it can never simulate a
    # partial read; verified empirically during this task's review.)
    from backend.app.api.custodian import _generate_and_persist

    fake = FakeCustodian(CustodianReply(content="Hello there.", tool_calls=[]))
    monkeypatch.setattr("backend.app.api.custodian.get_custodian", lambda: fake)

    async with session(seeded_user) as conn:
        custodian_session = await CustodianRepository(conn).create_session(
            user_id=seeded_user, model="gpt-4o-mini", provider="openai"
        )
        await CustodianRepository(conn).add_message(
            session_id=custodian_session.id, user_id=seeded_user, role="user", content="Hi"
        )

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _generate_and_persist(custodian_session.id, seeded_user, queue)
    )
    await asyncio.wait_for(task, timeout=5.0)

    async with session(seeded_user) as conn:
        messages = await CustodianRepository(conn).list_messages(custodian_session.id)

    assert any(m.role == "assistant" and m.content == "Hello there." for m in messages)

    async with session(seeded_user) as conn:
        await conn.execute(text("DELETE FROM custodian_messages"))
        await conn.execute(text("DELETE FROM custodian_sessions"))
