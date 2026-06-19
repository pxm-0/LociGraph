from __future__ import annotations

from typing import Any

from kernel.ingestion.base import ParsedFragment

_DEFAULT_CONFIDENCE = 1.0


class Normalizer:
    def normalize(self, fragments: list[ParsedFragment]) -> list[dict[str, Any]]:
        kept = [f for f in fragments if f.extracted_text and f.extracted_text.strip()]
        rows: list[dict[str, Any]] = []
        for i, frag in enumerate(kept):
            rows.append(
                {
                    "content": frag.extracted_text,
                    "observed_at": frag.timestamp,
                    "speaker": frag.author,
                    "context_before": kept[i - 1].extracted_text if i > 0 else None,
                    "context_after": (
                        kept[i + 1].extracted_text if i + 1 < len(kept) else None
                    ),
                    "confidence": _DEFAULT_CONFIDENCE,
                }
            )
        return rows
