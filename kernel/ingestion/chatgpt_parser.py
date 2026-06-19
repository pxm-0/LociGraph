from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kernel.ingestion.base import ParsedFragment


class ChatGptParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        conversations = json.loads(path.read_text(encoding="utf-8"))
        messages: list[dict[str, Any]] = []
        for conversation in conversations:
            mapping = conversation.get("mapping", {})
            for node in mapping.values():
                message = node.get("message")
                if message:
                    messages.append(message)

        # Stable sort by create_time, nulls last.
        messages.sort(key=lambda m: (m.get("create_time") is None, m.get("create_time") or 0))

        fragments: list[ParsedFragment] = []
        for message in messages:
            parts = message.get("content", {}).get("parts", []) or []
            text = "\n".join(str(p) for p in parts).strip()
            if not text:
                continue
            create_time = message.get("create_time")
            timestamp = (
                datetime.fromtimestamp(create_time, tz=UTC)
                if isinstance(create_time, int | float)
                else None
            )
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=text,
                    author=message.get("author", {}).get("role"),
                    timestamp=timestamp,
                    raw_payload=message,
                )
            )
        return fragments
