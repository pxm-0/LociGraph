from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.meta_parser import MetaParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_messages_in_time_order():
    frags = MetaParser().parse(FIXTURES / "meta_messages.json")
    # third message has no content -> skipped; sorted ascending by timestamp_ms
    assert [f.extracted_text for f in frags] == ["first", "second"]
    assert [f.author for f in frags] == ["Alice", "Bob"]
    assert frags[0].timestamp == datetime.fromtimestamp(1700000000, tz=UTC)
    assert [f.raw_index for f in frags] == [0, 1]
