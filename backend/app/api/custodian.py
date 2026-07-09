from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.auth.dependencies import get_current_user
from kernel.ai.custodian import CustodianSettings, ToolCallRecord, get_custodian
from kernel.db.custodian import CustodianRepository
from kernel.db.session import session
from kernel.models import CustodianMessage, CustodianSession

logger = logging.getLogger(__name__)

router = APIRouter()

# Fire-and-forget background tasks: Python only guarantees a task stays alive
# while something holds a strong reference to it, so a bare
# `asyncio.create_task(...)` risks the task being garbage-collected mid-flight.
# This module-level set is the standard workaround (add on create, discard on
# completion via a done-callback).
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class CreateSessionBody(BaseModel):
    title: str | None = None


class MessageBody(BaseModel):
    content: str


def _serialize_session(s: CustodianSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "title": s.title,
        "started_at": s.started_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "model": s.model,
        "provider": s.provider,
    }


def _serialize_message(m: CustodianMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "session_id": str(m.session_id),
        "role": m.role,
        "content": m.content,
        "tool_name": m.tool_name,
        "tool_input": m.tool_input,
        "tool_output": m.tool_output,
        "created_at": m.created_at.isoformat(),
    }


@router.post("/custodian/sessions")
async def create_custodian_session(
    body: CreateSessionBody, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    settings = CustodianSettings.from_env()
    async with session(user_id) as conn:
        created = await CustodianRepository(conn).create_session(
            user_id=user_id,
            model=settings.openai_custodian_model,
            provider=settings.active_ai_provider,
            title=body.title,
        )
    return _serialize_session(created)


@router.get("/custodian/sessions")
async def list_custodian_sessions(
    limit: int = 50, offset: int = 0, user_id: str = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        sessions = await CustodianRepository(conn).list_sessions(limit=limit, offset=offset)
    return [_serialize_session(s) for s in sessions]


@router.get("/custodian/sessions/{session_id}/messages")
async def get_custodian_messages(
    session_id: str, user_id: str = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        if await repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="not found")
        messages = await repo.list_messages(session_id)
    return [_serialize_message(m) for m in messages]


@router.post("/custodian/sessions/{session_id}/end")
async def end_custodian_session(
    session_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, Any]:
    async with session(user_id) as conn:
        ended = await CustodianRepository(conn).end_session(session_id)
        if ended is None:
            raise HTTPException(status_code=404, detail="not found or already ended")
    return _serialize_session(ended)


async def _generate_and_persist(
    session_id: UUID, user_id: str, queue: asyncio.Queue[dict[str, Any] | None]
) -> None:
    """Runs as a detached background task, independent of the HTTP response
    lifecycle — persists the reply regardless of whether the client is still
    listening. Puts SSE-shaped events on `queue`, then `None` to signal done."""
    try:
        async with session(user_id) as conn:
            repo = CustodianRepository(conn)
            history = [
                {"role": m.role, "content": m.content}
                for m in await repo.list_messages(session_id)
                if m.role in ("user", "assistant")
            ]
            custodian = get_custodian()

            async def on_token(delta: str) -> None:
                await queue.put({"event": "token", "data": {"delta": delta}})

            async def on_tool_call(record: ToolCallRecord) -> None:
                query = json.loads(record.tool_input).get("query", "")
                await queue.put(
                    {
                        "event": "tool_call",
                        "data": {"tool_name": record.tool_name, "query": query},
                    }
                )

            reply = await custodian.reply(
                conn, user_id, session_id, history, on_token, on_tool_call
            )

            for call in reply.tool_calls:
                await repo.add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="tool",
                    content="",
                    tool_name=call.tool_name,
                    tool_input=call.tool_input,
                    tool_output=call.tool_output,
                )
            await repo.add_message(
                session_id=session_id, user_id=user_id, role="assistant", content=reply.content
            )
        await queue.put({"event": "done", "data": {}})
    except Exception as exc:
        logger.warning("custodian reply failed for session %s: %s", session_id, exc)
        try:
            async with session(user_id) as conn:
                await CustodianRepository(conn).add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="system",
                    content="The Custodian couldn't respond. Please try again.",
                )
        except Exception:
            logger.exception("failed to persist custodian error message for session %s", session_id)
        await queue.put({"event": "error", "data": {"message": "generation failed"}})
    finally:
        await queue.put(None)


@router.post("/custodian/sessions/{session_id}/messages")
async def send_custodian_message(
    session_id: str, body: MessageBody, user_id: str = Depends(get_current_user)
) -> StreamingResponse:
    settings = CustodianSettings.from_env()
    async with session(user_id) as conn:
        repo = CustodianRepository(conn)
        custodian_session = await repo.get_session(session_id)
        if custodian_session is None:
            raise HTTPException(status_code=404, detail="not found")
        message_count = await repo.count_messages(session_id)
        if (
            custodian_session.ended_at is not None
            or message_count >= settings.custodian_max_messages_per_session
        ):
            if custodian_session.ended_at is None:
                await repo.end_session(session_id)
            raise HTTPException(
                status_code=409,
                detail="this conversation has reached its message limit — start a new one",
            )
        await repo.add_message(
            session_id=session_id, user_id=user_id, role="user", content=body.content
        )
        if custodian_session.title is None:
            await repo.set_title(session_id, body.content[:60])

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    _spawn(_generate_and_persist(UUID(session_id), user_id, queue))

    async def event_stream() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
