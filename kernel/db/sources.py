from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import Source


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    """Cast a SQLAlchemy RowMapping to the plain Mapping[str, Any] expected by models."""
    return row  # type: ignore[return-value]


_COLUMNS = (
    "id, user_id, source_type, original_filename, original_mime_type, "
    "checksum_sha256, file_size_bytes, raw_storage_path, import_status, "
    "imported_at, verified_at, metadata"
)


class SourceRepository(BaseRepository):
    async def create(
        self,
        user_id: str | UUID,
        source_type: str,
        checksum_sha256: str,
        *,
        original_filename: str | None = None,
        original_mime_type: str | None = None,
        file_size_bytes: int | None = None,
        raw_storage_path: str | None = None,
    ) -> Source:
        row = (
            await self.conn.execute(
                text(
                    f"""
                    INSERT INTO sources
                        (user_id, source_type, checksum_sha256, original_filename,
                         original_mime_type, file_size_bytes, raw_storage_path)
                    VALUES
                        (:user_id, :source_type, :checksum, :filename,
                         :mime, :size, :path)
                    RETURNING {_COLUMNS}
                    """
                ),
                {
                    "user_id": str(user_id),
                    "source_type": source_type,
                    "checksum": checksum_sha256,
                    "filename": original_filename,
                    "mime": original_mime_type,
                    "size": file_size_bytes,
                    "path": raw_storage_path,
                },
            )
        ).mappings().one()
        return Source.from_row(_as_mapping(row))

    async def get(self, source_id: str | UUID) -> Source | None:
        row = (
            await self.conn.execute(
                text(f"SELECT {_COLUMNS} FROM sources WHERE id = :id"),
                {"id": str(source_id)},
            )
        ).mappings().first()
        return Source.from_row(_as_mapping(row)) if row else None

    async def set_status(self, source_id: str | UUID, status: str) -> None:
        await self.conn.execute(
            text("UPDATE sources SET import_status = :status WHERE id = :id"),
            {"status": status, "id": str(source_id)},
        )

    async def mark_verified(self, source_id: str | UUID) -> None:
        await self.conn.execute(
            text(
                "UPDATE sources SET import_status = 'VERIFIED', verified_at = now() "
                "WHERE id = :id"
            ),
            {"id": str(source_id)},
        )

    async def update_storage_path(self, source_id: str | UUID, path: str) -> None:
        await self.conn.execute(
            text("UPDATE sources SET raw_storage_path = :p WHERE id = :id"),
            {"p": path, "id": str(source_id)},
        )

    async def purge(self, source_id: str | UUID) -> bool:
        row = (
            await self.conn.execute(
                text(
                    "UPDATE sources SET import_status = 'PURGED', purged_at = now(), "
                    "raw_storage_path = NULL WHERE id = :id RETURNING id"
                ),
                {"id": str(source_id)},
            )
        ).mappings().first()
        return row is not None

    async def list(self, limit: int = 50, offset: int = 0) -> list[Source]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM sources "
                    "ORDER BY imported_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [Source.from_row(_as_mapping(r)) for r in rows]

    async def count(self) -> int:
        result: int = (await self.conn.execute(text("SELECT count(*) FROM sources"))).scalar_one()
        return result
