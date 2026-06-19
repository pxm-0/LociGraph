from __future__ import annotations

from kernel.ingestion.base import Parser, SourceType
from kernel.ingestion.chatgpt_parser import ChatGptParser
from kernel.ingestion.html_parser import HtmlParser
from kernel.ingestion.json_parser import JsonParser
from kernel.ingestion.markdown_parser import MarkdownParser
from kernel.ingestion.meta_parser import MetaParser
from kernel.ingestion.pdf_parser import PdfParser

_PARSERS: dict[str, Parser] = {
    SourceType.JSON: JsonParser(),
    SourceType.MARKDOWN: MarkdownParser(),
    SourceType.HTML: HtmlParser(),
    SourceType.PDF: PdfParser(),
    SourceType.CHATGPT: ChatGptParser(),
    SourceType.META: MetaParser(),
}


def get_parser(source_type: str) -> Parser:
    try:
        return _PARSERS[source_type]
    except KeyError:
        raise ValueError(f"unknown source_type: {source_type!r}") from None
