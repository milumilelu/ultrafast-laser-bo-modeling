from ultrafast_memory.rag.metadata_filter import apply_metadata_filters, enforce_purpose


def test_metadata_filter_and_rejected_guard():
    hits = [
        {"chunk_id": "a", "review_status": "pending_review", "metadata_json": '{"material":"glass_wafer"}'},
        {"chunk_id": "b", "review_status": "rejected", "metadata_json": '{"material":"glass_wafer"}'},
    ]
    assert [hit["chunk_id"] for hit in apply_metadata_filters(hits, {"material": "glass_wafer"})] == ["a"]
    assert not enforce_purpose({"metadata": {"not_usable_for": ["direct_parameter_recommendation"]}}, "direct_parameter_recommendation")


def test_purpose_policy_separates_background_parameter_and_formal_authority():
    background = {
        "review_status": "accepted",
        "evidence_level": "reviewed_background",
        "metadata": {"target_level": "LEVEL_1_RAG_BACKGROUND"},
    }
    literature = {
        "review_status": "accepted",
        "evidence_level": "literature_evidence",
        "metadata": {"target_level": "LEVEL_2_LITERATURE_EVIDENCE"},
    }
    prior = {
        "review_status": "approved",
        "evidence_level": "process_prior",
        "metadata": {"target_level": "LEVEL_3_PROCESS_PRIOR"},
    }

    assert enforce_purpose(background, "literature_background")
    assert not enforce_purpose(background, "parameter_recommendation")
    assert enforce_purpose(literature, "parameter_recommendation")
    assert not enforce_purpose(literature, "formal_process")
    assert enforce_purpose(prior, "formal_process")
