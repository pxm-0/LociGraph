from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> User:
        return cls(id=row["id"], email=row["email"], created_at=row.get("created_at"))


@dataclass(frozen=True, slots=True)
class Source:
    id: UUID
    user_id: UUID
    source_type: str
    checksum_sha256: str
    import_status: str
    original_filename: str | None = None
    original_mime_type: str | None = None
    file_size_bytes: int | None = None
    raw_storage_path: str | None = None
    verified_at: datetime | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Source:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_type=row["source_type"],
            checksum_sha256=row["checksum_sha256"],
            import_status=row["import_status"],
            original_filename=row.get("original_filename"),
            original_mime_type=row.get("original_mime_type"),
            file_size_bytes=row.get("file_size_bytes"),
            raw_storage_path=row.get("raw_storage_path"),
            verified_at=row.get("verified_at"),
            metadata=row.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class Fragment:
    id: UUID
    user_id: UUID
    source_id: UUID
    raw_index: int | None = None
    extracted_text: str | None = None
    timestamp: datetime | None = None
    author: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Fragment:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            raw_index=row.get("raw_index"),
            extracted_text=row.get("extracted_text"),
            timestamp=row.get("timestamp"),
            author=row.get("author"),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    id: UUID
    user_id: UUID
    content: str
    confidence: float
    status: str
    created_at: datetime
    source_id: UUID | None = None
    fragment_id: UUID | None = None
    observed_at: datetime | None = None
    speaker: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Observation:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            confidence=float(row["confidence"]),
            status=row["status"],
            created_at=row["created_at"],
            source_id=row.get("source_id"),
            fragment_id=row.get("fragment_id"),
            observed_at=row.get("observed_at"),
            speaker=row.get("speaker"),
        )


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    user_id: UUID
    job_type: str
    status: str
    attempts: int = 0
    error: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Job:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            job_type=row["job_type"],
            status=row["status"],
            attempts=row.get("attempts", 0),
            error=row.get("error"),
        )
