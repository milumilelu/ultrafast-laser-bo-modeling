from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from ultrafast_agent.process_recommendations import ProcessRecommendationService
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.trial.closed_loop import TrialClosedLoopService
from ultrafast_memory.trial.decision import TrialDecisionService


def _search_space() -> dict:
    return {
        "variables": {
            "laser_power_W": {"mode": "optimizable", "lower": 1.0, "upper": 8.0},
            "scan_speed_mm_s": {"mode": "optimizable", "lower": 100.0, "upper": 800.0},
        },
        "fixed_parameters": {"frequency_kHz": 200, "passes": 4},
        "forbidden_parameters": {"pulse_width_fs": "equipment fixed"},
        "derived_constraints": [],
        "outcome_constraints": [{"metric": "kerf_width_um", "max": 100}],
        "source_trace": [{"source": "equipment_hard_boundary"}],
        "search_space_version": "search-space-v1",
        "feasibility_status": "ready",
        "blocking_reasons": [],
        "conflicting_sources": [],
        "warnings": [],
    }


def _feedback(recommendation: dict, run_id: str, kerf: float, alarms=None) -> dict:
    recipe = dict(recommendation["complete_recipe"])
    return {
        "run_id": run_id,
        "cam_applied_parameters": recipe,
        "machine_actual_parameters": recipe,
        "measurements": {"kerf_width_um": kerf},
        "parameter_units": {
            "laser_power_W": "W",
            "scan_speed_mm_s": "mm/s",
            "frequency_kHz": "kHz",
            "passes": "count",
        },
        "measurement_units": {"kerf_width_um": "um"},
        "constraint_results": {"no_delamination": True},
        "run_status": "completed",
        "alarms": list(alarms or []),
        "measurement_method": "optical_microscopy_v1",
        "material": "CFRP",
        "process_type": "cutting",
        "equipment_revision": "equipment-r1",
        "risk_state": "normal",
    }


def _campaign(service: TrialClosedLoopService) -> dict:
    return service.create_campaign(
        task_id="task-closed-loop",
        workflow_id="workflow-closed-loop",
        task_spec={
            "material": "CFRP",
            "process_type": "cutting",
            "thickness_mm": 3,
            "quality_requirement": "no_delamination",
            "cut_length_mm": 100,
            "efficiency_requirement": "none",
            "auxiliary": "compressed_air",
            "layer_cut_allowed": True,
        },
        search_space=_search_space(),
        current_recipe={"frequency_kHz": 200, "passes": 4},
        parameter_units={
            "laser_power_W": "W",
            "scan_speed_mm_s": "mm/s",
            "frequency_kHz": "kHz",
            "passes": "count",
        },
        equipment_revision="equipment-r1",
        targets={"kerf_width_um": {"max": 100}},
        constraints={"no_delamination": True},
        session_id="session-closed-loop",
    )


def test_trial_feedback_bo_next_recommendation_and_production_closure(isolated_root):
    service = TrialClosedLoopService()
    created = _campaign(service)
    campaign_id = created["campaign"]["campaign_id"]
    assert set(created["strategies"]) == {"conservative", "balanced", "exploratory"}

    first = service.select_strategy(campaign_id, "balanced", {
        "bo": {
            "recommended_parameters": {"laser_power_W": 4.0, "scan_speed_mm_s": 320.0},
            "model_status": "hybrid_rule_bo",
            "model_version": "bo-model-v1",
            "dataset_version": "dataset-v0",
            "bo_run_id": "bo-run-1",
        },
        "approved_prior": {"recommended_parameters": {"laser_power_W": 2.0}},
        "rag": {"recommended_parameters": {"laser_power_W": 1.5}},
    })
    rec1 = first["recommendation"]
    rec1_snapshot = deepcopy(rec1)
    assert rec1["iteration_number"] == 1
    assert rec1["parent_recommendation_id"] is None
    assert rec1["recommendation_source"] == "bo_parameter_recommendation"
    assert rec1["source_run_id"] == "bo-run-1"
    assert set(rec1["complete_recipe"]) == {
        "laser_power_W", "scan_speed_mm_s", "frequency_kHz", "passes",
    }

    observation1 = service.submit_feedback(
        campaign_id, rec1["recommendation_id"],
        _feedback(rec1, "external-trial-run-1", 120),
    )
    assert observation1["eligibility"]["eligible"] is True
    assert observation1["training_sample_created"] is False
    stored1 = observation1["observation"]
    assert stored1["recommended_parameters"] == rec1["complete_recipe"]
    assert stored1["cam_applied_parameters"] == rec1["complete_recipe"]
    assert stored1["machine_actual_parameters"] == rec1["complete_recipe"]

    advanced1 = service.approve_feedback_and_advance(
        campaign_id,
        stored1["observation_id"],
        approved_by="process-engineer",
        next_bo_result={
            "recommended_parameters": {"laser_power_W": 4.2, "scan_speed_mm_s": 350.0},
            "model_status": "hybrid_rule_bo",
            "model_version": "bo-model-v2",
            "bo_run_id": "bo-run-2",
        },
    )
    assert advanced1["decision"]["decision"] == "CONTINUE_TRIAL"
    rec2 = advanced1["next_recommendation"]
    assert rec2["iteration_number"] == 2
    assert rec2["parent_recommendation_id"] == rec1["recommendation_id"]
    assert rec2["dataset_version"] == advanced1["dataset_version"]["dataset_version_id"]
    assert ProcessRecommendationService().get(rec1["recommendation_id"]) == rec1_snapshot

    observation2 = service.submit_feedback(
        campaign_id, rec2["recommendation_id"],
        _feedback(rec2, "external-trial-run-2", 90),
    )
    advanced2 = service.approve_feedback_and_advance(
        campaign_id,
        observation2["observation"]["observation_id"],
        approved_by="process-engineer",
    )
    assert advanced2["decision"]["decision"] == "TRIAL_SUCCEEDED"
    assert len(advanced2["dataset_version"]["sample_ids"]) == 2
    candidate = advanced2["production_candidate"]
    assert candidate["stage"] == "production_candidate"
    assert candidate["status"] == "pending_review"

    approved = service.approve_production(
        campaign_id, candidate["recommendation_id"], approved_by="task-owner"
    )
    assert approved["recommendation"]["stage"] == "production_approved"
    assert approved["campaign"]["business_state"] == "READY_FOR_EXTERNAL_PROCESS"
    assert "machine_control" not in approved["cam_export"] or not approved["cam_export"]["machine_control"]

    external = service.report_external_processing_started(campaign_id)
    assert external["business_state"] == "WAITING_EXTERNAL_RESULT"
    assert external["metadata"]["external_status_source"] == "user_reported"
    closed = service.submit_final_inspection(
        campaign_id,
        measurements={"kerf_width_um": 95},
        constraint_results={"no_delamination": True},
        files=["inspection.json"],
    )
    assert closed["quality_decision"] == "PASS"
    assert closed["campaign"]["business_state"] == "COMPLETED"
    assert closed["report"]["status"] == "completed"

    trace = service.get_campaign(campaign_id)["events"]
    required = {
        "trial_strategy_offered", "trial_strategy_selected", "recommendation_created",
        "cam_export_created", "trial_feedback_received", "bo_eligibility_evaluated",
        "dataset_version_created", "next_recommendation_created", "trial_decision_made",
        "production_candidate_created", "production_approved", "final_inspection_received",
        "quality_decision_made",
    }
    assert required <= {event["event_type"] for event in trace}
    assert [event["sequence"] for event in trace] == list(range(1, len(trace) + 1))


def test_ineligible_feedback_cannot_enter_dataset(isolated_root):
    service = TrialClosedLoopService()
    campaign_id = _campaign(service)["campaign"]["campaign_id"]
    selected = service.select_strategy(campaign_id, "conservative", {
        "bo": {
            "recommended_parameters": {"laser_power_W": 3.0, "scan_speed_mm_s": 300.0},
            "model_status": "rule_based_cold_start",
        },
    })
    feedback = service.submit_feedback(
        campaign_id,
        selected["recommendation"]["recommendation_id"],
        _feedback(selected["recommendation"], "alarm-run", 120, alarms=["laser_fault"]),
    )
    assert feedback["eligibility"]["eligible"] is False
    assert "blocking_alarm_present" in feedback["eligibility"]["blocking_reasons"]
    with pytest.raises(ValueError, match="ineligible TrialObservation"):
        service.approve_feedback_and_advance(
            campaign_id,
            feedback["observation"]["observation_id"],
            approved_by="engineer",
        )


def test_llm_trial_fallback_cannot_be_production_approved(isolated_root):
    service = TrialClosedLoopService()
    campaign_id = _campaign(service)["campaign"]["campaign_id"]
    selected = service.select_strategy(campaign_id, "exploratory", {
        "llm_fallback": {
            "recommended_parameters": {"laser_power_W": 2.0, "scan_speed_mm_s": 200.0},
            "model_status": "trial_only",
        },
    })
    assert selected["recommendation"]["recommendation_source"] == "llm_trial_fallback"
    recommendation = selected["recommendation"]
    with pytest.raises(ValueError, match="LLM trial fallback"):
        ProcessRecommendationService().create(
            task_id="task-closed-loop",
            workflow_id="workflow-closed-loop",
            task_spec={"material": "CFRP", "process_type": "cutting"},
            bo_result={"recommended_parameters": recommendation["optimized_parameters"]},
            search_space=_search_space(),
            current_recipe=recommendation["complete_recipe"],
            stage="production_approved",
            parameter_units={
                "laser_power_W": "W", "scan_speed_mm_s": "mm/s",
                "frequency_kHz": "kHz", "passes": "count",
            },
            recommendation_source="llm_trial_fallback",
        )


def test_trial_campaign_api_exposes_persistent_closed_loop(isolated_root):
    client = TestClient(app)
    response = client.post("/api/v1/trial-campaigns", json={
        "task_id": "api-task",
        "workflow_id": "api-workflow",
        "task_spec": {"material": "CFRP", "process_type": "cutting"},
        "search_space": _search_space(),
        "current_recipe": {"frequency_kHz": 200, "passes": 4},
        "parameter_units": {
            "laser_power_W": "W", "scan_speed_mm_s": "mm/s",
            "frequency_kHz": "kHz", "passes": "count",
        },
        "equipment_revision": "equipment-r1",
        "targets": {"kerf_width_um": {"max": 100}},
        "constraints": {"no_delamination": True},
    })
    assert response.status_code == 200
    campaign_id = response.json()["campaign"]["campaign_id"]

    selected = client.post(f"/api/v1/trial-campaigns/{campaign_id}/strategy", json={
        "strategy": "balanced",
        "recommendation_options": {"bo": {
            "recommended_parameters": {"laser_power_W": 4.0, "scan_speed_mm_s": 320.0},
            "model_status": "hybrid_rule_bo",
        }},
    })
    assert selected.status_code == 200
    assert selected.json()["recommendation"]["iteration_number"] == 1
    read = client.get(f"/api/v1/trial-campaigns/{campaign_id}")
    assert read.status_code == 200
    assert len(read.json()["iterations"]) == 1


@pytest.mark.parametrize(("measurements", "constraints", "iteration", "expected"), [
    ({"kerf": 90}, {"safe": True}, 1, "TRIAL_SUCCEEDED"),
    ({"kerf": 120}, {"safe": True}, 1, "CONTINUE_TRIAL"),
    ({"kerf": 90}, {"safe": False}, 1, "TRIAL_BLOCKED"),
    ({}, {"safe": True}, 3, "ESCALATE_REVIEW"),
])
def test_trial_decision_service_has_only_governed_outcomes(
    measurements, constraints, iteration, expected
):
    result = TrialDecisionService.decide(
        measurements=measurements,
        targets={"kerf": {"max": 100}},
        constraints=constraints,
        iteration_number=iteration,
        iteration_budget=3,
    )
    assert result["decision"] == expected
