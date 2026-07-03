import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def test_ignores_non_json_zip_members_like_dat_files(tmp_path):
    # Real exports also include binary attachments (voice messages, images)
    # with arbitrary, non-UTF-8 content — these must not affect parsing.
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURES / "conversations.json", arcname="conversations.json")
        zf.writestr("assets/voice-message-a1b2c3.dat", b"\x00\x01\xff\xfe not valid utf-8 \x80\x81")

    frags = ChatGptParser().parse(zip_path)

    assert [f.extracted_text for f in frags] == ["hello there", "hi, how can I help?"]
    assert [f.author for f in frags] == ["user", "assistant"]


def test_finds_conversations_json_nested_in_a_subdirectory(tmp_path):
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURES / "conversations.json", arcname="chatgpt-export/conversations.json")

    frags = ChatGptParser().parse(zip_path)

    assert [f.extracted_text for f in frags] == ["hello there", "hi, how can I help?"]
    assert [f.author for f in frags] == ["user", "assistant"]


def test_raises_a_clear_error_when_conversations_json_is_missing(tmp_path):
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("user.json", "{}")

    with pytest.raises(ValueError) as exc_info:
        ChatGptParser().parse(zip_path)

    assert "conversations.json" in str(exc_info.value)


def test_merges_sharded_conversations_files_when_no_single_conversations_json(tmp_path):
    # Large real exports (observed: ~1GB, 1000+ files) split conversations across
    # conversations-000.json, conversations-001.json, ... instead of one
    # conversations.json — each shard is a JSON array of conversations, same shape.
    zip_path = tmp_path / "export.zip"
    shard_0 = [
        {
            "title": "shard0",
            "mapping": {
                "a1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["from shard zero"]},
                        "create_time": 1700000000,
                    }
                },
            },
        }
    ]
    shard_1 = [
        {
            "title": "shard1",
            "mapping": {
                "b1": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["from shard one"]},
                        "create_time": 1700000060,
                    }
                },
            },
        }
    ]
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations-000.json", json.dumps(shard_0))
        zf.writestr("conversations-001.json", json.dumps(shard_1))
        zf.writestr("shared_conversations.json", "[]")  # present in real exports, must be ignored

    frags = ChatGptParser().parse(zip_path)

    assert [f.extracted_text for f in frags] == ["from shard zero", "from shard one"]
    assert [f.author for f in frags] == ["user", "assistant"]
