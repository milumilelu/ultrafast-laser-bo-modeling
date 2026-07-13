from __future__ import annotations

import csv
import json

from ultrafast_bo.application.services import RecommendationService
from ultrafast_memory.bo.bo_engine_adapter import call_bo_recommendation


BOUNDS = {
    "laser_power_W": [1.0, 20.0],
    "frequency_kHz": [50.0, 500.0],
    "scan_speed_mm_s": [10.0, 1000.0],
    "passes": [1, 20],
}


def _machine():
    return {"active": True, "machine_bounds": BOUNDS, "revision_id": "eqrev-test"}


def _samples(count: int):
    rows = []
    for index in range(count):
        power = 2.0 + index * 0.25
        frequency = 80.0 + index * 4
        speed = 100.0 + index * 8
        passes = 1 + index % 20
        rows.append(
            {
                "sample_id": f"sample-{index}",
                "valid_for_training": True,
                "x_parameters": {
                    "laser_power_W": power,
                    "frequency_kHz": frequency,
                    "scan_speed_mm_s": speed,
                    "passes": passes,
                },
                "y_metrics": {"quality_score": 0.4 * power + 0.01 * frequency - 0.001 * speed},
            }
        )
    return rows


def test_cold_start_is_bounded_and_does_not_claim_bo():
    result = RecommendationService().recommend({}, [], _machine())

    assert result["model_status"] == "rule_based_cold_start"
    assert result["bo_invoked"] is False
    for name, value in result["recommended_parameters"].items():
        assert BOUNDS[name][0] <= value <= BOUNDS[name][1]


def test_readiness_governs_cold_hybrid_and_data_driven_modes():
    low_support = RecommendationService().recommend({"random_seed": 7}, _samples(12), _machine())
    hybrid = RecommendationService().recommend({"random_seed": 7}, _samples(40), _machine())
    data_driven = RecommendationService().recommend(
        {
            "random_seed": 7,
            "validation_metrics": {
                "prediction_interval_coverage": 0.94,
                "uncertainty_calibration_error": 0.01,
            },
        },
        _samples(40), _machine(),
    )

    assert low_support["model_status"] == "rule_based_cold_start"
    assert low_support["bo_invoked"] is False
    assert hybrid["model_status"] == "hybrid_rule_bo"
    assert hybrid["bo_invoked"] is True
    assert hybrid["prediction"]["metric"] == "quality_score"
    assert data_driven["model_status"] == "data_driven_bo"
    assert data_driven["bo_invoked"] is True


def test_only_approved_prior_can_narrow_search_bounds():
    priors = [
        {"parameter_name": "laser_power_W", "lower_bound": 2, "upper_bound": 3},
        {
            "approval_id": "approval-1",
            "parameter_name": "frequency_kHz",
            "lower_bound": 100,
            "upper_bound": 120,
        },
    ]

    result = RecommendationService().recommend({}, [], _machine(), priors)

    assert result["knowledge_approval_ids"] == ["approval-1"]
    assert 100 <= result["recommended_parameters"]["frequency_kHz"] <= 120
    assert result["recommended_parameters"]["laser_power_W"] > 3
    assert any(item["status"] == "ignored_unapproved" for item in result["audit_trace"])


def test_agent_export_adapter_calls_real_service(tmp_path):
    path = tmp_path / "training.csv"
    fieldnames = ["sample_id", "valid_for_training", "x_parameters_json", "y_metrics_json"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in _samples(12):
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "valid_for_training": 1,
                    "x_parameters_json": json.dumps(row["x_parameters"]),
                    "y_metrics_json": json.dumps(row["y_metrics"]),
                }
            )

    result = call_bo_recommendation(
        {"machine_bounds": BOUNDS, "equipment_revision": "eqrev-explicit"}, str(path)
    )

    assert result["model_status"] == "rule_based_cold_start"
    assert result["bo_invoked"] is False
    assert result["training_csv_path"] == str(path)
    assert result["machine_bounds_revision"] == "eqrev-explicit"


def test_agent_bo_blocks_without_equipment_bounds(isolated_root, tmp_path):
    result = call_bo_recommendation({}, str(tmp_path / "missing.csv"))

    assert result["model_status"] == "blocked"
    assert result["bo_invoked"] is False


def test_bo_cannot_use_literature_parameters_without_gate():
    blocked = RecommendationService().recommend(
        {"literature_parameters_used": True}, _samples(12), _machine()
    )
    allowed = RecommendationService().recommend(
        {
            "literature_parameters_used": True,
            "knowledge_gate_decision": {
                "status": "allowed",
                "reused_approval": {"approval_id": "approval-gate-1"},
            },
        },
        _samples(12),
        _machine(),
    )

    assert blocked["model_status"] == "blocked"
    assert blocked["bo_invoked"] is False
    assert allowed["model_status"] == "rule_based_cold_start"
    assert allowed["bo_invoked"] is False
    assert allowed["knowledge_approval_ids"] == ["approval-gate-1"]
