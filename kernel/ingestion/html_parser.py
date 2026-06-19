from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from kernel.ingestion.base import ParsedFragment

_BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]


class HtmlParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        fragments: list[ParsedFragment] = []
        for element in soup.find_all(_BLOCK_TAGS):
            content = element.get_text(separator=" ", strip=True)
            if not content:
                continue
            fragments.append(
                ParsedFragment(
                    raw_index=len(fragments),
                    extracted_text=content,
                    metadata={"tag": element.name},
                )
            )
        return fragments
