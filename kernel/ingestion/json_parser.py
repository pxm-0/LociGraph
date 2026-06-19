from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kernel.ingestion.base import ParsedFragment


class JsonParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        return [self._fragment(i, item) for i, item in enumerate(items)]

    @staticmethod
    def _fragment(index: int, item: Any) -> ParsedFragment:
        if isinstance(item, str):
            text = item
            payload: dict[str, Any] = {"value": item}
        elif isinstance(item, dict):
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
            payload = item
        else:
            text = json.dumps(item, ensure_ascii=False)
            payload = {"value": item}
        return ParsedFragment(raw_index=index, extracted_text=text, raw_payload=payload)
