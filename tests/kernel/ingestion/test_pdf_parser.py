from pathlib import Path

from fpdf import FPDF

from kernel.ingestion.pdf_parser import PdfParser


def _make_pdf(path: Path, pages: list[str]) -> None:
    pdf = FPDF()
    pdf.set_font("helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, text)
    pdf.output(str(path))


def test_emits_one_fragment_per_nonempty_page(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["Page one content.", "Page two content."])
    frags = PdfParser().parse(pdf_path)
    assert len(frags) == 2
    assert "Page one content." in frags[0].extracted_text
    assert "Page two content." in frags[1].extracted_text
    assert frags[0].metadata == {"page": 1}
    assert frags[1].metadata == {"page": 2}
