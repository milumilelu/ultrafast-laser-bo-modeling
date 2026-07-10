from ultrafast_memory.literature.structured_loader import load_structured_deliverables


def test_structured_loader_normalizes_doi_and_defaults_review(mixed_literature_root):
    root = mixed_literature_root / "deliverables" / "tgv"
    loaded = load_structured_deliverables(root)
    assert loaded["cards"][0].doi == "10.1234/tgv.test"
    assert loaded["cards"][0].review_status == "pending_review"
    assert loaded["candidates"][0]["candidate_id"] == "candidate_tgv_test"
