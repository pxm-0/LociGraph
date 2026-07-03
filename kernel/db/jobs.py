from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Job

_COLUMNS = (
    "id, user_id, job_type, status, attempts, error, "
    "created_at, started_at, completed_at, items_completed, items_total"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    """Cast a SQLAlchemy RowMapping to the plain Mapping[str, Any] expected by models."""
    return row  # type: ignore[return-value]


class JobRepository(BaseRepository):
    async def create(
        self,
        user_id: str | UUID,
        job_type: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO jobs (user_id, job_type, payload)
                    VALUES (:user_id, :job_type, CAST(:payload AS JSONB))
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "job_type": job_type,
                    "payload": json.dumps(payload or {}),
                },
            )
        ).mappings().one()
        return Job.from_row(_as_mapping(row))

    async def mark_running(self, job_id: str | UUID) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET status = 'running', started_at = now() WHERE id = :id"
            ),
            {"id": str(job_id)},
        )

    async def mark_completed(
        self, job_id: str | UUID, result: dict[str, Any] | None = None
    ) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET status = 'completed', completed_at = now(), "
                "result = CAST(:result AS JSONB) WHERE id = :id"
            ),
            {"id": str(job_id), "result": json.dumps(result or {})},
        )

    async def update_progress(
        self, job_id: str | UUID, *, items_completed: int, items_total: int
    ) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET items_completed = :items_completed, "
                "items_total = :items_total WHERE id = :id"
            ),
            {
                "id": str(job_id),
                "items_completed": items_completed,
                "items_total": items_total,
            },
        )

    async def record_attempt(self, job_id: str | UUID, error: str) -> None:
        await self.conn.execute(
            text(
                "UPDATE jobs SET attempts = attempts + 1, status = 'failed', "
                "error = :error WHERE id = :id"
            ),
            {"id": str(job_id), "error": error},
        )

    async def get(self, job_id: str | UUID) -> Job | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM jobs WHERE id = :id"),
                {"id": str(job_id)},
            )
        ).mappings().first()
        return Job.from_row(_as_mapping(row)) if row else None

    async def find_active_job_for_source(
        self,
        job_type: str,
        source_id: str | UUID,
        *,
        exclude_job_id: str | UUID | None = None,
    ) -> UUID | None:
        """Id of a pending/running job of `job_type` for this source, if any.

        Used to stop a second extraction/ingestion from starting on top of
        one already in flight for the same source (e.g. a stale browser tab
        that doesn't know a job was already triggered elsewhere).
        """
        clauses = [
            "job_type = :job_type",
            "status IN ('pending', 'running')",
            "payload ->> 'source_id' = :source_id",
        ]
        params: dict[str, Any] = {"job_type": job_type, "source_id": str(source_id)}
        if exclude_job_id is not None:
            clauses.append("id != :exclude_job_id")
            params["exclude_job_id"] = str(exclude_job_id)

        result = await self.conn.execute(
            text(f"SELECT id FROM jobs WHERE {' AND '.join(clauses)} LIMIT 1"),
            params,
        )
        row = result.first()
        return row[0] if row else None

    async def count_by_statuses(self, statuses: list[str]) -> int:
        if not statuses:
            return 0
        params = {f"status_{i}": status for i, status in enumerate(statuses)}
        placeholders = ", ".join(f":status_{i}" for i in range(len(statuses)))
        result: int = (
            await self.conn.execute(
                text(f"SELECT count(*) FROM jobs WHERE status IN ({placeholders})"),
                params,
            )
        ).scalar_one()
        return result
