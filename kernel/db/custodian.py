from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import CustodianMessage, CustodianSession

_SESSION_COLUMNS = "id, user_id, title, started_at, ended_at, model, provider"
_MESSAGE_COLUMNS = (
    "id, session_id, user_id, role, content, tool_name, tool_input, "
    "tool_output, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class CustodianRepository(BaseRepository):
    async def create_session(
        self,
        *,
        user_id: str | UUID,
        model: str,
        provider: str,
        title: str | None = None,
    ) -> CustodianSession:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_sessions (user_id, title, model, provider)
                    VALUES (:user_id, :title, :model, :provider)
                    RETURNING {_SESSION_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "title": strip_nul_bytes(title),
                    "model": model,
                    "provider": provider,
                },
            )
        ).mappings().one()
        return CustodianSession.from_row(_as_mapping(row))

    async def get_session(self, session_id: str | UUID) -> CustodianSession | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_SESSION_COLUMNS} FROM custodian_sessions WHERE id = :id"),
                {"id": str(session_id)},
            )
        ).mappings().first()
        return CustodianSession.from_row(_as_mapping(row)) if row else None

    async def list_sessions(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[CustodianSession]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_SESSION_COLUMNS} FROM custodian_sessions "
                    "ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [CustodianSession.from_row(_as_mapping(r)) for r in rows]

    async def end_session(self, session_id: str | UUID) -> CustodianSession | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE custodian_sessions SET ended_at = now()
                    WHERE id = :id AND ended_at IS NULL
                    RETURNING {_SESSION_COLUMNS}
                    """
                ),
                {"id": str(session_id)},
            )
        ).mappings().first()
        return CustodianSession.from_row(_as_mapping(row)) if row else None

    async def set_title(self, session_id: str | UUID, title: str) -> None:
        await self.conn.execute(
            text(
                "UPDATE custodian_sessions SET title = :title "
                "WHERE id = :id AND title IS NULL"
            ),
            {"id": str(session_id), "title": strip_nul_bytes(title)},
        )

    async def add_message(
        self,
        *,
        session_id: str | UUID,
        user_id: str | UUID,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_input: str | None = None,
        tool_output: str | None = None,
    ) -> CustodianMessage:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_messages
                        (session_id, user_id, role, content, tool_name, tool_input, tool_output)
                    VALUES
                        (:session_id, :user_id, :role, :content, :tool_name, :tool_input, :tool_output)
                    RETURNING {_MESSAGE_COLUMNS}
                    """
                ),
                {
                    "session_id": str(session_id),
                    "user_id": str(user_id),
                    "role": role,
                    "content": strip_nul_bytes(content),
                    "tool_name": tool_name,
                    "tool_input": strip_nul_bytes(tool_input),
                    "tool_output": strip_nul_bytes(tool_output),
                },
            )
        ).mappings().one()
        return CustodianMessage.from_row(_as_mapping(row))

    async def list_messages(self, session_id: str | UUID) -> list[CustodianMessage]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_MESSAGE_COLUMNS} FROM custodian_messages "
                    "WHERE session_id = :session_id ORDER BY created_at ASC"
                ),
                {"session_id": str(session_id)},
            )
        ).mappings().all()
        return [CustodianMessage.from_row(_as_mapping(r)) for r in rows]

    async def count_messages(self, session_id: str | UUID) -> int:
        result: int = (
            await self.conn.execute(
                text(
                    "SELECT count(*) FROM custodian_messages WHERE session_id = :session_id"
                ),
                {"session_id": str(session_id)},
            )
        ).scalar_one()
        return result
