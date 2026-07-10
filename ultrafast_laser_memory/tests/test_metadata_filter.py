from ultrafast_memory.rag.metadata_filter import apply_metadata_filters, enforce_purpose


def test_metadata_filter_and_rejected_guard():
    hits = [
        {"chunk_id": "a", "review_status": "pending_review", "metadata_json": '{"material":"glass_wafer"}'},
        {"chunk_id": "b", "review_status": "rejected", "metadata_json": '{"material":"glass_wafer"}'},
    ]
    assert [hit["chunk_id"] for hit in apply_metadata_filters(hits, {"material": "glass_wafer"})] == ["a"]
    assert not enforce_purpose({"metadata": {"not_usable_for": ["direct_parameter_recommendation"]}}, "direct_parameter_recommendation")
