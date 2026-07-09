from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class SourceType:
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    CHATGPT = "chatgpt"
    META = "meta"
    CUSTODIAN = "custodian"
    ALL: tuple[str, ...] = (JSON, MARKDOWN, HTML, PDF, CHATGPT, META)


@dataclass(frozen=True, slots=True)
class ParsedFragment:
    """One unit of extracted content from a source, before persistence."""

    raw_index: int
    extracted_text: str
    timestamp: datetime | None = None
    author: str | None = None
    raw_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def to_fragment_row(self) -> dict[str, Any]:
        """Shape consumed by FragmentRepository.bulk_insert (extra keys ignored)."""
        return {
            "raw_index": self.raw_index,
            "extracted_text": self.extracted_text,
            "timestamp": self.timestamp,
            "author": self.author,
            "raw_payload": self.raw_payload,
        }


@runtime_checkable
class Parser(Protocol):
    def parse(self, path: Path) -> list[ParsedFragment]: ...
