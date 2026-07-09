from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository, strip_nul_bytes
from kernel.models import CustodianLoggedItem

ITEM_TYPES = {
    "observation",
    "note",
    "claim",
    "task",
    "concept_candidate",
    "reality_assertion",
    "perception_assertion",
    "contradiction",
    "importance_signal",
    "contradiction_classification",
}
STATUSES = {"proposed", "accepted", "rejected", "superseded"}

_COLUMNS = (
    "id, user_id, session_id, message_id, item_type, target_id, content, "
    "status, created_at, resolved_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class CustodianLoggedItemRepository(BaseRepository):
    async def create(
        self,
        *,
        user_id: str | UUID,
        session_id: str | UUID,
        item_type: str,
        content: dict[str, Any],
        target_id: str | UUID | None = None,
        message_id: str | UUID | None = None,
    ) -> CustodianLoggedItem:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO custodian_logged_items
                        (user_id, session_id, message_id, item_type, target_id, content)
                    VALUES
                        (:user_id, :session_id, :message_id, :item_type, :target_id,
                         CAST(:content AS JSONB))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "session_id": str(session_id),
                    "message_id": str(message_id) if message_id else None,
                    "item_type": item_type,
                    "target_id": str(target_id) if target_id else None,
                    "content": json.dumps(strip_nul_bytes(content)),
                },
            )
        ).mappings().one()
        return CustodianLoggedItem.from_row(_as_mapping(row))

    async def get(self, item_id: str | UUID) -> CustodianLoggedItem | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM custodian_logged_items WHERE id = :id"),
                {"id": str(item_id)},
            )
        ).mappings().first()
        return CustodianLoggedItem.from_row(_as_mapping(row)) if row else None

    async def list_for_session(self, session_id: str | UUID) -> list[CustodianLoggedItem]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM custodian_logged_items "
                    "WHERE session_id = :session_id ORDER BY created_at ASC"
                ),
                {"session_id": str(session_id)},
            )
        ).mappings().all()
        return [CustodianLoggedItem.from_row(_as_mapping(r)) for r in rows]

    async def resolve(
        self, item_id: str | UUID, status: str, *, target_id: str | UUID | None = None
    ) -> CustodianLoggedItem | None:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    UPDATE custodian_logged_items
                    SET status = :status, resolved_at = now(),
                        target_id = COALESCE(:target_id, target_id)
                    WHERE id = :id AND status = 'proposed'
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "id": str(item_id),
                    "status": status,
                    "target_id": str(target_id) if target_id else None,
                },
            )
        ).mappings().first()
        return CustodianLoggedItem.from_row(_as_mapping(row)) if row else None

    async def set_message_id(self, item_id: str | UUID, message_id: str | UUID) -> None:
        await self.conn.execute(
            text("UPDATE custodian_logged_items SET message_id = :message_id WHERE id = :id"),
            {"id": str(item_id), "message_id": str(message_id)},
        )
