from datetime import UTC, datetime

from kernel.ingestion.base import ParsedFragment
from kernel.ingestion.normalizer import Normalizer


def _frag(i, text, author=None, ts=None):
    return ParsedFragment(raw_index=i, extracted_text=text, author=author, timestamp=ts)


def test_normalize_sets_context_window_and_defaults():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    frags = [_frag(0, "one", "a", ts), _frag(1, "two", "b"), _frag(2, "three")]
    rows = Normalizer().normalize(frags)
    assert [r["content"] for r in rows] == ["one", "two", "three"]
    assert rows[0]["context_before"] is None
    assert rows[0]["context_after"] == "two"
    assert rows[1]["context_before"] == "one"
    assert rows[1]["context_after"] == "three"
    assert rows[2]["context_after"] is None
    assert rows[0]["speaker"] == "a"
    assert rows[0]["observed_at"] == ts
    assert all(r["confidence"] == 1.0 for r in rows)


def test_normalize_skips_empty_and_recomputes_window():
    frags = [_frag(0, "keep1"), _frag(1, "   "), _frag(2, "keep2")]
    rows = Normalizer().normalize(frags)
    assert [r["content"] for r in rows] == ["keep1", "keep2"]
    # window computed over kept fragments only
    assert rows[0]["context_after"] == "keep2"
    assert rows[1]["context_before"] == "keep1"
