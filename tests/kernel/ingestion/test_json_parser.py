from pathlib import Path

from kernel.ingestion.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_top_level_array_into_one_fragment_per_item():
    frags = JsonParser().parse(FIXTURES / "sample.json")
    assert len(frags) == 2
    assert frags[0].raw_index == 0
    assert frags[1].raw_index == 1
    assert "first entry" in frags[0].extracted_text
    assert frags[0].raw_payload == {"text": "first entry", "author": "alice"}


def test_parses_top_level_object_into_single_fragment(tmp_path):
    p = tmp_path / "obj.json"
    p.write_text('{"a": 1, "b": "two"}', encoding="utf-8")
    frags = JsonParser().parse(p)
    assert len(frags) == 1
    assert frags[0].raw_index == 0
    assert frags[0].raw_payload == {"a": 1, "b": "two"}


def test_string_array_items_use_the_string_as_text(tmp_path):
    p = tmp_path / "strs.json"
    p.write_text('["hello", "world"]', encoding="utf-8")
    frags = JsonParser().parse(p)
    assert [f.extracted_text for f in frags] == ["hello", "world"]
    assert frags[0].raw_payload == {"value": "hello"}
