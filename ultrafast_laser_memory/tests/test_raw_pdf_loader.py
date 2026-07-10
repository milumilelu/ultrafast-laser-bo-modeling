import pytest

from ultrafast_memory.literature.raw_pdf_loader import parse_pdf


def test_raw_pdf_loader_preserves_pages_and_flags_scans(mixed_literature_root, tmp_path):
    parsed = parse_pdf(mixed_literature_root / "raw" / "tgv_paper.pdf", tmp_path / "archive")
    assert parsed.parse_status == "parsed"
    assert [page.page_number for page in parsed.pages] == [1, 2, 3]
    assert parsed.metadata["doi"] == "10.1234/tgv.test"

    fitz = pytest.importorskip("fitz")
    blank = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(blank)
    doc.close()
    assert parse_pdf(blank, tmp_path / "archive").parse_status == "needs_ocr"
