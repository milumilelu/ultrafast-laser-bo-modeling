from __future__ import annotations

from typing import Any

from ultrafast_domain.trial import (
    TrialMode,
    assess_trial_need,
    design_trial_plan,
    evaluate_trial_result,
    select_trial_mode,
)
from ultrafast_integrations.storage.trial_repository import TrialRepository


class TrialApplicationService:
    def __init__(self, repository: TrialRepository | None = None):
        self.repository = repository or TrialRepository()

    def assess(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_spec = {"task_id": task_id, **(payload.get("task_spec") or {})}
        assessment = assess_trial_need(
            task_spec,
            evidence_status=payload.get("evidence_status", "insufficient"),
            approved_prior_count=int(payload.get("approved_prior_count", 0)),
            similar_case_count=int(payload.get("similar_case_count", 0)),
            valid_sample_count=int(payload.get("valid_sample_count", 0)),
            equipment_revision_unchanged=bool(payload.get("equipment_revision_unchanged", False)),
        )
        return {"task_id": task_id, **assessment.to_dict()}

    def select(self, task_id: str, assessment: dict[str, Any], trial_mode: str) -> dict[str, Any]:
        mode = select_trial_mode(assessment, trial_mode)
        return {
            "task_id": task_id,
            "trial_mode": mode.value,
            "recommended_mode": assessment.get("recommended_mode"),
            "user_overrode_recommendation": mode.value != assessment.get("recommended_mode"),
        }

    def create_plan(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        draft = design_trial_plan(
            task_id,
            {"task_id": task_id, **(payload.get("task_spec") or {})},
            TrialMode(payload["trial_mode"]),
            payload.get("machine_bounds") or {},
            payload.get("domain_pack"),
            payload.get("approved_parameter_candidates"),
        )
        result = self.repository.create_plan(draft.to_dict())
        result["warnings"] = draft.warnings
        return result

    def get_plan(self, trial_plan_id: str) -> dict[str, Any]:
        return self.repository.get_plan(trial_plan_id)

    def start_execution(self, trial_plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.start_execution(
            trial_plan_id,
            payload["equipment_revision"],
            payload.get("actual_parameters") or {},
            payload.get("actual_path") or {},
            payload.get("monitoring_summary") or {},
        )

    def create_result(self, execution_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_result(
            execution_id, payload.get("measurements") or {}, payload.get("defects") or []
        )

    def evaluate(self, result_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.repository.get_result(result_id)
        execution = self.repository.get_execution(result["execution_id"])
        plan = self.repository.get_plan(execution["trial_plan_id"])
        evaluation = evaluate_trial_result(
            plan["acceptance_criteria"],
            result["measurements"],
            result["defects"],
            execution["monitoring_summary"],
        )
        unlocked = bool(evaluation["formal_process_unlocked"])
        if evaluation["decision"] == "conditional_pass" and payload.get("confirm_conditional"):
            unlocked = True
        return self.repository.evaluate_result(
            result_id,
            evaluation,
            payload.get("reviewer_comment"),
            unlocked,
        )
