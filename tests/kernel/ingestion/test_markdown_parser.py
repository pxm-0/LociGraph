from pathlib import Path

from kernel.ingestion.markdown_parser import MarkdownParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_emits_a_fragment_per_block():
    frags = MarkdownParser().parse(FIXTURES / "sample.md")
    texts = [f.extracted_text for f in frags]
    assert "Title" in texts
    assert "First paragraph with some text." in texts
    assert "Second paragraph here." in texts
    assert [f.raw_index for f in frags] == list(range(len(frags)))


def test_skips_empty_blocks(tmp_path):
    p = tmp_path / "spaced.md"
    p.write_text("para one\n\n\n\npara two\n", encoding="utf-8")
    frags = MarkdownParser().parse(p)
    assert [f.extracted_text for f in frags] == ["para one", "para two"]
