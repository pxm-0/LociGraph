from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

from kernel.ai.custodian import CustodianReply, ToolCallRecord
from kernel.db.custodian import CustodianRepository
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
