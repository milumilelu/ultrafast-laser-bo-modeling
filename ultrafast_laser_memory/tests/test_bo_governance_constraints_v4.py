from __future__ import annotations

from ultrafast_bo.application.governance import (
    BODatasetSliceService,
    BOEligibilityService,
    BOReadinessAssessmentService,
)
from ultrafast_bo.application.search_space import ConstraintEvaluator, SearchSpaceBuilder, project_candidate
from ultrafast_bo.application.search_space import outcome_feasibility_probability
from ultrafast_bo.application.lifecycle import BOModelRegistry
from ultrafast_bo.domain.models import BOSample


def _sample(sample_id: str, material: str = "diamond", process: str = "milling", valid: bool = True):
    return BOSample(
        sample_id, {"laser_power_W": 3.0, "frequency_kHz": 200.0}, {"Ra_um": 0.4}, valid,
        material, process, equipment_profile_id="laser-1", target_metric="Ra_um",
        measurement_method="profilometer", task_id="task-1", batch_id="batch-1",
    )


def test_dataset_slice_never_mixes_material_process_or_unapproved_source():
    values = [_sample("ok"), _sample("sic", "SiC"), _sample("cut", process="cutting"), _sample("bad", valid=False)]
    selected, report = BODatasetSliceService().select(
        values, material="diamond", process_type="milling", equipment_profile_id="laser-1",
        target_metric="Ra_um", measurement_method="profilometer", feature_schema_version="1.0",
    )
    assert [sample.sample_id for sample in selected] == ["ok"]
    assert report.excluded_counts_by_reason == {
        "material_mismatch": 1, "not_approved_for_training": 1, "process_type_mismatch": 1,
    }


def test_feedback_is_candidate_until_eligibility_and_approval():
    report = BOEligibilityService().assess(
        {"task_id": "t", "recommendation_id": "r", "machine_actual_parameters": {"laser_power_W": 2},
         "measurements": {"Ra_um": 0.4}, "run_status": "failed", "measurement_method": "profilometer"}
    )
    assert not report.eligible and "run_not_completed" in report.blocking_reasons


def test_readiness_is_not_sample_count_only():
    repeated = [_sample(str(index)) for index in range(40)]
    report = BOReadinessAssessmentService().assess(
        repeated, target_metric="Ra_um", parameter_bounds={"laser_power_W": [0, 10], "frequency_kHz": [100, 500]},
    )
    assert report.model_status != "data_driven_bo"
    assert "poor_parameter_coverage" in report.warnings


def test_fixed_parameter_context_partial_optimization_and_step_projection():
    space = SearchSpaceBuilder().compile(
        {"parameter_constraints": {}},
        {"revision_id": "eq-v1", "machine_bounds": {"laser_power_W": [0, 10], "frequency_kHz": [50, 500], "passes": {"bounds": [1, 5], "step": 1}}},
        {
            "laser_power_W": {"mode": "optimizable", "lower": 2, "upper": 6},
            "frequency_kHz": {"mode": "fixed", "value": 200},
            "passes": {"mode": "integer", "lower": 1, "upper": 5, "step": 1},
        }, [], {}, "trial_cut",
    )
    candidate = project_candidate({"laser_power_W": 7, "passes": 2.7}, space)
    assert set(space.variables) == {"laser_power_W", "passes"}
    assert candidate == {"frequency_kHz": 200, "laser_power_W": 6.0, "passes": 3}


def test_device_bounds_cannot_be_relaxed_and_conflict_is_explicit():
    space = SearchSpaceBuilder().compile(
        {"parameter_constraints": {"laser_power_W": [0, 6]}},
        {"machine_bounds": {"laser_power_W": [0, 10]}},
        {"laser_power_W": {"mode": "bounded", "lower": 0, "upper": 20}},
        [{"prior_id": "p1", "parameter_name": "laser_power_W", "lower_bound": 8, "upper_bound": 12, "status": "approved"}],
        {}, "trial_cut",
    )
    assert space.feasibility_status == "infeasible_search_space"
    conflict = space.conflicting_sources[0]
    assert {item["source"] for item in conflict["lower_candidates"]} >= {"equipment_hard_boundary", "user_policy", "approved_process_prior"}


def test_pulse_energy_constraint_uses_documented_units():
    evaluator = ConstraintEvaluator()
    assert evaluator.evaluate(
        {"laser_power_W": 5, "frequency_kHz": 200},
        {"constraint_type": "pulse_energy_max", "threshold": 30, "unit": "uJ"},
    )
    assert not evaluator.evaluate(
        {"laser_power_W": 10, "frequency_kHz": 200},
        {"constraint_type": "pulse_energy_max", "threshold": 30, "unit": "uJ"},
    )


def test_conditional_parameter_and_no_optimizable_parameters():
    builder = SearchSpaceBuilder()
    inactive = builder.compile(
        {}, {"machine_bounds": {"fill_pattern": {"allowed_values": ["contour"]}, "hatch_spacing_um": [1, 9]}},
        {
            "fill_pattern": {"mode": "fixed", "value": "contour"},
            "hatch_spacing_um": {"mode": "conditional", "lower": 1, "upper": 9,
                                 "condition": {"if_parameter": "fill_pattern", "equals": "raster"}},
        }, [], {}, "trial_cut",
    )
    assert "hatch_spacing_um" not in project_candidate({"hatch_spacing_um": 4}, inactive)
    fixed = builder.compile(
        {}, {"machine_bounds": {"frequency_kHz": [50, 500]}},
        {"frequency_kHz": {"mode": "fixed", "value": 200}}, [], {}, "trial_cut",
    )
    assert fixed.feasibility_status == "no_optimizable_parameters"


def test_outcome_probability_and_model_lifecycle_replay():
    probabilities, overall = outcome_feasibility_probability(
        {"Ra_um": {"mean": 0.4, "std": 0.1}},
        [{"metric": "Ra_um", "operator": "max", "threshold": 0.5}],
    )
    assert 0.8 < probabilities["Ra_um"] < 0.9 and overall == probabilities["Ra_um"]

    registry = BOModelRegistry()
    dataset = registry.register_dataset(["b", "a"], {"material": "diamond"}, "1.0")
    model = registry.register_model(training_dataset_version=dataset.dataset_version_id)
    import pytest
    with pytest.raises(KeyError):
        registry.activate("diamond-milling", model.model_version_id, "missing", "expert")
    evaluation = registry.record_evaluation(model.model_version_id, dataset.dataset_version_id, {"rmse": 0.1}, passed=True)
    assert registry.activate("diamond-milling", model.model_version_id, evaluation.evaluation_id, "expert").status == "active"
    challenger = registry.register_model(training_dataset_version=dataset.dataset_version_id)
    challenger_eval = registry.record_evaluation(
        challenger.model_version_id, dataset.dataset_version_id, {"rmse": 0.08}, passed=True,
        baseline_model_version_id=model.model_version_id,
    )
    registry.activate("diamond-milling", challenger.model_version_id, challenger_eval.evaluation_id, "expert")
    assert registry.rollback("diamond-milling").model_version_id == model.model_version_id
    trace = {
        "bo_run_id": "run-1", "training_sample_ids": ["a", "b"], "dataset_version": dataset.dataset_version_id,
        "model_version": model.model_version_id, "feature_schema_version": "1.0", "objective_version": "1.0",
        "acquisition_version": "ucb-1.0", "random_seed": 42, "code_commit": "abc",
        "equipment_profile_version": "eq-1", "approved_prior_versions": [], "result": {"value": 1},
    }
    registry.record_run(trace)
    assert registry.replay_bo_run("run-1") == trace
