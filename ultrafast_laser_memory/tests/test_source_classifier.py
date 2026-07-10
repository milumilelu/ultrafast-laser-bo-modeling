from ultrafast_memory.literature.source_classifier import classify_source_root, discover_structured_roots


def test_source_classifier_recommends_structured_first(mixed_literature_root):
    result = classify_source_root(mixed_literature_root)
    assert result["has_raw_pdfs"] is True
    assert result["has_literature_cards"] is True
    assert result["recommended_mode"] == "structured_first_with_pdf_backfill"
    assert len(discover_structured_roots(mixed_literature_root)) == 1
