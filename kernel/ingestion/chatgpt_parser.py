from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kernel.ingestion.base import ParsedFragment

_SHARD_NAME = re.compile(r"(^|/)conversations-\d+\.json$")


class ChatGptParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        conversations = self._read_conversations(path)
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

    @staticmethod
    def _read_conversations(path: Path) -> list[dict[str, Any]]:
        """OpenAI's real "Export data" download is a .zip containing
        conversations.json (plus files this parser doesn't need); detect by
        content rather than extension since the stored filename is whatever
        the user uploaded it as. Large exports instead shard conversations
        across conversations-000.json, conversations-001.json, etc. — same
        per-file shape (a JSON array of conversations), just split up."""
        if not zipfile.is_zipfile(path):
            result: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
            return result

        with zipfile.ZipFile(path) as zf:
            try:
                raw = zf.read("conversations.json").decode("utf-8")
                exact: list[dict[str, Any]] = json.loads(raw)
                return exact
            except KeyError:
                pass

            nested = next((n for n in zf.namelist() if n.endswith("/conversations.json")), None)
            if nested is not None:
                found: list[dict[str, Any]] = json.loads(zf.read(nested).decode("utf-8"))
                return found

            shards = sorted(n for n in zf.namelist() if _SHARD_NAME.search(n))
            if shards:
                conversations: list[dict[str, Any]] = []
                for shard in shards:
                    conversations.extend(json.loads(zf.read(shard).decode("utf-8")))
                return conversations

            raise ValueError("no conversations.json found in ChatGPT export zip")
