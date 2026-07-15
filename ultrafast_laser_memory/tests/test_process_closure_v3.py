from ultrafast_memory.process_workflow.closure import (
    archive_gate,
    bo_sample_eligibility,
    quality_decision,
)


def test_incomplete_inspection_is_not_failed_and_cannot_close():
    result = quality_decision(["delamination_width", "kerf_width"], {"kerf_width": 1}, {})
    assert result["decision"] == "INCOMPLETE_DATA"
    assert not result["can_close"]


def test_invalid_result_cannot_enter_bo_and_archive_needs_report():
    assert not bo_sample_eligibility({"validation_status": "invalid"})["eligible"]
    allowed, missing = archive_gate(
        quality_decided=True,
        report_generated=False,
        experiment_record_validated=True,
    )
    assert not allowed and missing == ["task_report"]
