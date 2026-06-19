from __future__ import annotations

from pathlib import Path

import pdfplumber

from kernel.ingestion.base import ParsedFragment


class PdfParser:
    def parse(self, path: Path) -> list[ParsedFragment]:
        fragments: list[ParsedFragment] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                fragments.append(
                    ParsedFragment(
                        raw_index=len(fragments),
                        extracted_text=text,
                        metadata={"page": page_number},
                    )
                )
        return fragments
