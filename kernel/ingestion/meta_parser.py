from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.base import ParsedFragment


class MetaParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = sorted(
            data.get("messages", []), key=lambda m: m.get("timestamp_ms", 0)
        )
        fragments: list[ParsedFragment] = []
        for message in messages:
            content = (message.get("content") or "").strip()
            if not content:
                continue
            timestamp_ms = message.get("timestamp_ms")
            timestamp = (
                datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
                if isinstance(timestamp_ms, int | float)
                else None
            )
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    author=message.get("sender_name"),
                    timestamp=timestamp,
                    raw_payload=message,
                )
            )
        return fragments
