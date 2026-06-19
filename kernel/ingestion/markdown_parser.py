from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import mistune

from kernel.ingestion.base import ParsedFragment

_BLOCK_TYPES = {"heading", "paragraph", "block_code"}


def _token_text(token: dict[str, Any]) -> str:
    """Recursively collect plain text from a mistune 3.x token."""
    if "raw" in token:
        return str(token["raw"])
    children = token.get("children")
    if isinstance(children, list):
        return "".join(_token_text(child) for child in children)
    return ""


class MarkdownParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        text = path.read_text(encoding="utf-8")
        # renderer=None yields the token list (mistune 3.x).
        md = mistune.create_markdown(renderer=None)
        tokens = cast(list[dict[str, Any]], md(text))
        fragments: list[ParsedFragment] = []
        for token in tokens:
            if token.get("type") not in _BLOCK_TYPES:
                continue
            content = _token_text(token).strip()
            if not content:
                continue
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    metadata={"block_type": token.get("type")},
                )
            )
        return fragments
