from __future__ import annotations

from typing import Any


def quality_decision(required_metrics: list[str], measurements: dict[str, Any],
                     constraint_results: dict[str, bool]) -> dict[str, Any]:
    missing = [name for name in required_metrics if measurements.get(name) is None]
    failed = [name for name, passed in constraint_results.items() if not passed]
    passed = [name for name, passed in constraint_results.items() if passed]
    if missing:
        decision = "INCOMPLETE_DATA"
    elif failed:
        decision = "FAIL"
    else:
        decision = "PASS"
    return {"decision": decision, "passed_metrics": passed, "failed_metrics": failed,
            "missing_metrics": missing, "can_close": decision == "PASS"}


def bo_sample_eligibility(record: dict[str, Any]) -> dict[str, Any]:
    required = ["task_id", "execution_id", "equipment_revision", "material_batch", "parameters",
                "measurements", "quality_decision", "fidelity_level"]
    missing = [key for key in required if record.get(key) in (None, "", {})]
    valid_decisions = {"PASS", "FAIL", "NEEDS_REVIEW"}
    reasons = [f"missing:{key}" for key in missing]
    if record.get("quality_decision") not in valid_decisions:
        reasons.append("quality_not_decided")
    if record.get("validation_status") != "valid":
        reasons.append("result_not_validated")
    return {"eligible": not reasons, "status": "approved_for_bo" if not reasons else "excluded", "reasons": reasons}


def archive_gate(*, quality_decided: bool, report_generated: bool, experiment_record_validated: bool) -> tuple[bool, list[str]]:
    missing = []
    if not quality_decided:
        missing.append("quality_decision")
    if not report_generated:
        missing.append("task_report")
    if not experiment_record_validated:
        missing.append("validated_experiment_record")
    return not missing, missing
