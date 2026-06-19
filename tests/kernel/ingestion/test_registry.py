from pathlib import Path

import pytest

from kernel.ingestion.base import Parser, SourceType
from kernel.ingestion.normalizer import Normalizer
from kernel.ingestion.registry import get_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_every_source_type_routes_to_a_parser():
    for source_type in SourceType.ALL:
        parser = get_parser(source_type)
        assert isinstance(parser, Parser)


def test_unknown_source_type_raises_valueerror():
    with pytest.raises(ValueError, match="bogus"):
        get_parser("bogus")


def test_end_to_end_parse_then_normalize_json():
    parser = get_parser(SourceType.JSON)
    fragments = parser.parse(FIXTURES / "sample.json")
    rows = Normalizer().normalize(fragments)
    assert len(rows) == 2
    assert all("content" in r and r["confidence"] == 1.0 for r in rows)
    assert rows[0]["context_after"] == fragments[1].extracted_text


def test_end_to_end_chatgpt_fragments_have_authors_and_timestamps():
    parser = get_parser(SourceType.CHATGPT)
    fragments = parser.parse(FIXTURES / "conversations.json")
    rows = Normalizer().normalize(fragments)
    assert [r["speaker"] for r in rows] == ["user", "assistant"]
    assert rows[0]["observed_at"] is not None
