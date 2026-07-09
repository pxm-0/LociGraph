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
    imported_at: datetime | None = None
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
            imported_at=row.get("imported_at"),
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
class Claim:
    id: UUID
    user_id: UUID
    source_id: UUID
    observation_id: UUID
    claim_text: str
    claim_type: str
    assertion_type: str
    confidence: float
    extraction_method: str
    status: str
    created_at: datetime
    model_name: str | None = None
    prompt_version: str | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Claim:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            observation_id=row["observation_id"],
            claim_text=row["claim_text"],
            claim_type=row["claim_type"],
            assertion_type=row["assertion_type"],
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
            model_name=row.get("model_name"),
            prompt_version=row.get("prompt_version"),
            status=row["status"],
            created_at=row["created_at"],
            metadata=row.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class SemanticVector:
    id: UUID
    user_id: UUID
    claim_id: UUID
    model_name: str
    created_at: datetime
    embedding: list[float]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SemanticVector:
        raw = row["embedding"]
        parsed = (
            [float(x) for x in raw.strip("[]").split(",")]
            if isinstance(raw, str)
            else list(raw)
        )
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            claim_id=row["claim_id"],
            model_name=row["model_name"],
            created_at=row["created_at"],
            embedding=parsed,
        )


@dataclass(frozen=True, slots=True)
class SimilarClaim:
    claim: Claim
    similarity: float


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    id: UUID
    user_id: UUID
    source_id: UUID
    claim_id: UUID
    candidate_name: str
    concept_type: str
    confidence: float
    extraction_method: str
    status: str
    created_at: datetime
    rationale: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ConceptCandidate:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            claim_id=row["claim_id"],
            candidate_name=row["candidate_name"],
            concept_type=row["concept_type"],
            rationale=row.get("rationale"),
            confidence=float(row["confidence"]),
            extraction_method=row["extraction_method"],
            model_name=row.get("model_name"),
            prompt_version=row.get("prompt_version"),
            status=row["status"],
            created_at=row["created_at"],
            metadata=row.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class Concept:
    id: UUID
    user_id: UUID
    concept_name: str
    concept_type: str
    status: str
    created_at: datetime
    description: str | None = None
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Concept:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_name=row["concept_name"],
            concept_type=row["concept_type"],
            description=row.get("description"),
            status=row["status"],
            created_at=row["created_at"],
            metadata=row.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class ClaimConceptEdge:
    id: UUID
    user_id: UUID
    claim_id: UUID
    concept_id: UUID
    concept_candidate_id: UUID
    confidence: float
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ClaimConceptEdge:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            claim_id=row["claim_id"],
            concept_id=row["concept_id"],
            concept_candidate_id=row["concept_candidate_id"],
            confidence=float(row["confidence"]),
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class CustodianSession:
    id: UUID
    user_id: UUID
    title: str | None
    started_at: datetime
    ended_at: datetime | None
    model: str
    provider: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianSession:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            title=row.get("title"),
            started_at=row["started_at"],
            ended_at=row.get("ended_at"),
            model=row["model"],
            provider=row["provider"],
        )


@dataclass(frozen=True, slots=True)
class CustodianMessage:
    id: UUID
    session_id: UUID
    user_id: UUID
    role: str
    content: str
    tool_name: str | None
    tool_input: str | None
    tool_output: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianMessage:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            role=row["role"],
            content=row["content"],
            tool_name=row.get("tool_name"),
            tool_input=row.get("tool_input"),
            tool_output=row.get("tool_output"),
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class Contradiction:
    id: UUID
    user_id: UUID
    concept_id: UUID
    claim_a_id: UUID
    claim_b_id: UUID
    similarity: float
    classification: str
    rationale: str
    created_at: datetime
    classified_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Contradiction:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_id=row["concept_id"],
            claim_a_id=row["claim_a_id"],
            claim_b_id=row["claim_b_id"],
            similarity=float(row["similarity"]),
            classification=row["classification"],
            rationale=row["rationale"],
            created_at=row["created_at"],
            classified_at=row.get("classified_at"),
        )


@dataclass(frozen=True, slots=True)
class Revision:
    id: UUID
    user_id: UUID
    concept_id: UUID
    contradiction_id: UUID | None
    source: str
    previous_description: str | None
    new_description: str
    rationale: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Revision:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_id=row["concept_id"],
            contradiction_id=row.get("contradiction_id"),
            source=row["source"],
            previous_description=row.get("previous_description"),
            new_description=row["new_description"],
            rationale=row.get("rationale"),
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    user_id: UUID
    job_type: str
    status: str
    attempts: int = 0
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    items_completed: int | None = None
    items_total: int | None = None
    heartbeat_at: datetime | None = None
    result: Mapping[str, Any] | None = None
    source_id: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Job:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            job_type=row["job_type"],
            status=row["status"],
            attempts=row.get("attempts", 0),
            error=row.get("error"),
            created_at=row.get("created_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            items_completed=row.get("items_completed"),
            items_total=row.get("items_total"),
            heartbeat_at=row.get("heartbeat_at"),
            result=row.get("result"),
            source_id=row.get("source_id"),
        )


@dataclass(frozen=True, slots=True)
class CustodianLoggedItem:
    id: UUID
    user_id: UUID
    session_id: UUID
    item_type: str
    content: Mapping[str, Any]
    status: str
    created_at: datetime
    message_id: UUID | None = None
    target_id: UUID | None = None
    resolved_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CustodianLoggedItem:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            item_type=row["item_type"],
            content=row["content"],
            status=row["status"],
            created_at=row["created_at"],
            message_id=row.get("message_id"),
            target_id=row.get("target_id"),
            resolved_at=row.get("resolved_at"),
        )


@dataclass(frozen=True, slots=True)
class Note:
    id: UUID
    user_id: UUID
    content: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Note:
        return cls(
            id=row["id"], user_id=row["user_id"], content=row["content"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ImportanceSignal:
    id: UUID
    user_id: UUID
    target_type: str
    target_id: UUID
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ImportanceSignal:
        return cls(
            id=row["id"], user_id=row["user_id"], target_type=row["target_type"],
            target_id=row["target_id"], created_at=row["created_at"],
        )
