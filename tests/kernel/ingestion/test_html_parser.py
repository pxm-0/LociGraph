from pathlib import Path

from kernel.ingestion.html_parser import HtmlParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_block_text_in_order():
    frags = HtmlParser().parse(FIXTURES / "sample.html")
    texts = [f.extracted_text for f in frags]
    assert texts == ["Heading One", "A paragraph of text.", "Item A", "Item B"]
    assert [f.raw_index for f in frags] == [0, 1, 2, 3]


def test_excludes_script_and_style(tmp_path):
    p = tmp_path / "s.html"
    p.write_text(
        "<body><style>a{}</style><p>keep</p><script>x()</script></body>",
        encoding="utf-8",
    )
    frags = HtmlParser().parse(p)
    assert [f.extracted_text for f in frags] == ["keep"]
