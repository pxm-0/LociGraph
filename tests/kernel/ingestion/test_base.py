from datetime import UTC, datetime

from kernel.ingestion.base import ParsedFragment, SourceType


def test_to_fragment_row_exposes_repo_keys():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    frag = ParsedFragment(
        raw_index=0, extracted_text="hello", timestamp=ts, author="me"
    )
    row = frag.to_fragment_row()
    assert row["raw_index"] == 0
    assert row["extracted_text"] == "hello"
    assert row["timestamp"] == ts
    assert row["author"] == "me"


def test_parsed_fragment_is_immutable():
    frag = ParsedFragment(raw_index=0, extracted_text="x")
    try:
        frag.extracted_text = "y"  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised


def test_source_type_all_contains_every_type():
    assert set(SourceType.ALL) == {
        SourceType.JSON,
        SourceType.MARKDOWN,
        SourceType.HTML,
        SourceType.PDF,
        SourceType.CHATGPT,
        SourceType.META,
    }
