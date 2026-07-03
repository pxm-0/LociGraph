import zipfile
from datetime import UTC, datetime
from pathlib import Path

from kernel.ingestion.chatgpt_parser import ChatGptParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_messages_in_time_order_skipping_empty():
    frags = ChatGptParser().parse(FIXTURES / "conversations.json")
    # n3 has empty parts -> skipped; remaining ordered by create_time
    assert [f.extracted_text for f in frags] == ["hello there", "hi, how can I help?"]
    assert [f.author for f in frags] == ["user", "assistant"]
    assert frags[0].timestamp == datetime.fromtimestamp(1700000000, tz=UTC)
    assert [f.raw_index for f in frags] == [0, 1]


def test_extracts_messages_from_a_real_export_zip(tmp_path):
    # OpenAI's actual "Export data" download is a .zip containing
    # conversations.json (plus other files this parser doesn't need) —
    # not a bare JSON file. Build one from the same fixture content.
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURES / "conversations.json", arcname="conversations.json")
        zf.writestr("user.json", "{}")  # present in real exports, must be ignored

    frags = ChatGptParser().parse(zip_path)

    assert [f.extracted_text for f in frags] == ["hello there", "hi, how can I help?"]
    assert [f.author for f in frags] == ["user", "assistant"]
