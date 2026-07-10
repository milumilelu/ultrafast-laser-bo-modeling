from __future__ import annotations

import pytest

from ultrafast_domain.trial import (
    TrialMode,
    assess_trial_need,
    design_trial_plan,
    evaluate_trial_result,
    select_trial_mode,
)


def test_simple_trial_recommended_for_new_low_sample_task():
    assessment = assess_trial_need(
        {"first_material": True, "complex_geometry": True},
        evidence_status="insufficient",
        approved_prior_count=0,
        valid_sample_count=4,
    )

    assert assessment.recommended_mode == TrialMode.SIMPLE
    assert TrialMode.SKIP not in assessment.allowed_modes
    assert "validated_samples_below_10" in assessment.reasons


def test_full_trial_recommended_for_matched_case_needing_path_validation():
    assessment = assess_trial_need(
        {"full_path_validation_required": True},
        evidence_status="sufficient",
        approved_prior_count=2,
        similar_case_count=3,
        valid_sample_count=20,
        equipment_revision_unchanged=True,
    )

    assert assessment.recommended_mode == TrialMode.FULL


def test_skip_only_allowed_for_exact_verified_repeat():
    assessment = assess_trial_need(
        {
            "exact_repeat": True,
            "complete_qualified_record": True,
            "user_allows_skip": True,
        },
        evidence_status="sufficient",
        approved_prior_count=1,
        equipment_revision_unchanged=True,
    )

    assert assessment.recommended_mode == TrialMode.SKIP
    assert select_trial_mode(assessment, "skip_trial") == TrialMode.SKIP
    unsafe = assess_trial_need({}, evidence_status="insufficient")
    with pytest.raises(ValueError):
        select_trial_mode(unsafe, "skip_trial")


def test_simple_and_full_plan_have_representative_geometry_and_stop_conditions():
    bounds = {"laser_power_W": [1, 10], "frequency_kHz": [50, 500], "passes": [1, 10]}
    simple = design_trial_plan(
        "task-crl",
        {"process_type": "CRL", "targets": {"form_error_max_um": 2.0}},
        "simple_trial_cut",
        bounds,
        "crl",
    )
    full = design_trial_plan(
        "task-crl",
        {"process_type": "CRL"},
        "full_trial_cut",
        bounds,
        "crl",
    )

    assert simple.representative_geometry["type"] == "shallow_paraboloid_segment_or_scaled_lens"
    assert simple.representative_geometry["full_geometry"] is False
    assert full.representative_geometry["full_geometry"] is True
    assert len(simple.parameter_matrix) == 5
    assert len(full.parameter_matrix) == 9
    assert {item["condition"] for item in full.stop_conditions} >= {
        "energy_drift",
        "crack_growth",
        "equipment_alarm",
    }


def test_trial_evaluation_pass_conditional_and_fail():
    criteria = [
        {"type": "critical_defects_absent", "required": True},
        {"metric": "depth_um", "operator": ">=", "value": 100, "required": True},
    ]

    passed = evaluate_trial_result(criteria, {"depth_um": 120}, [], {})
    conditional = evaluate_trial_result(criteria, {}, [], {})
    failed = evaluate_trial_result(
        criteria,
        {"depth_um": 120},
        [{"name": "crack", "severity": "critical"}],
        {},
    )

    assert passed["decision"] == "pass" and passed["formal_process_unlocked"] is True
    assert conditional["decision"] == "conditional_pass" and conditional["formal_process_unlocked"] is False
    assert failed["decision"] == "fail" and failed["formal_process_unlocked"] is False
