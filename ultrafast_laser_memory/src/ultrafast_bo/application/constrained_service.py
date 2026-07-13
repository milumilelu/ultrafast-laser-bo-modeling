from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from ultrafast_bo.application.formal_service import BORecommendationService
from ultrafast_bo.application.search_space import (
    ConstraintEvaluator,
    SearchSpaceBuilder,
    outcome_feasibility_probability,
    project_candidate,
)
from ultrafast_bo.domain.models import BOSample


class ConstrainedBORecommendationService:
    def __init__(self, *, builder: SearchSpaceBuilder | None = None, bo: BORecommendationService | None = None):
        self.builder = builder or SearchSpaceBuilder()
        self.bo = bo or BORecommendationService()
        self.constraints = ConstraintEvaluator()

    def recommend(
        self,
        *,
        task_spec: dict[str, Any],
        samples: Iterable[BOSample | dict[str, Any]],
        equipment_snapshot: dict[str, Any],
        parameter_policy: dict[str, Any],
        approved_priors: list[dict[str, Any]] | None = None,
        current_recipe: dict[str, Any] | None = None,
        trial_mode: str = "trial_cut",
    ) -> dict[str, Any]:
        space = self.builder.compile(
            task_spec, equipment_snapshot, parameter_policy, approved_priors,
            current_recipe or {}, trial_mode,
        )
        if space.feasibility_status == "infeasible_search_space":
            return {
                "status": "infeasible_search_space", "error_code": "infeasible_search_space",
                "blocking_reasons": space.blocking_reasons, "conflicting_sources": space.conflicting_sources,
                "suggested_next_actions": ["review conflicting task, user, equipment, and approved-prior constraints"],
                "search_space": space.to_dict(), "recommended_parameters": {}, "complete_recipe": {},
            }
        recipe = dict(current_recipe or {})
        recipe.update(space.fixed_parameters)
        if space.feasibility_status == "no_optimizable_parameters":
            return {
                "status": "no_optimizable_parameters", "error_code": "no_optimizable_parameters",
                "blocking_reasons": [], "warnings": ["current recipe was evaluated without running BO"],
                "search_space": space.to_dict(), "recommended_parameters": {}, "complete_recipe": recipe,
                "predictions": {}, "uncertainty": None, "model_status": "rule_based_cold_start",
                "model_version": None, "dataset_version": None, "objective_version": task_spec.get("objective_version", "1.0"),
            }
        scoped_samples = [sample for sample in samples if _matches_fixed(sample, space.fixed_parameters)]
        numeric_bounds = {
            name: [spec["lower"], spec["upper"]]
            for name, spec in space.variables.items()
            if spec["type"] in {"continuous", "integer", "conditional"}
        }
        formal_task = {
            **task_spec,
            "acquisition_version": task_spec.get("acquisition_version", "noisy_ei_feasibility-1.0"),
        }
        bo_result = self.bo.recommend(
            formal_task,
            scoped_samples,
            {**equipment_snapshot, "active": equipment_snapshot.get("active", True), "machine_bounds": numeric_bounds},
            approved_priors=[],  # priors have already been compiled; never apply twice
        )
        candidate = project_candidate(bo_result.get("recommended_parameters") or {}, space)
        if not self.constraints.all_satisfied(candidate, space.derived_constraints):
            alternative = self._legal_fallback(space, int(task_spec.get("random_seed", 42)))
            if alternative is None:
                return {
                    **bo_result, "status": "infeasible_search_space", "error_code": "infeasible_search_space",
                    "blocking_reasons": ["no candidate satisfies compiled coupling constraints"],
                    "search_space": space.to_dict(), "recommended_parameters": {}, "complete_recipe": {},
                }
            candidate = alternative
            bo_result.setdefault("warnings", []).append("surrogate candidate violated a coupling constraint; deterministic legal fallback selected")
        optimized = {name: candidate[name] for name in space.variables if name in candidate}
        complete = {**recipe, **optimized}
        prediction_map = _prediction_map(bo_result)
        constraint_probability, overall_probability = outcome_feasibility_probability(
            prediction_map, space.outcome_constraints
        )
        return {
            **bo_result,
            "status": "ready" if bo_result.get("status") != "blocked" else "blocked",
            "recommended_parameters": optimized,
            "complete_recipe": complete,
            "fixed_parameters": space.fixed_parameters,
            "forbidden_parameters": space.forbidden_parameters,
            "search_space": space.to_dict(),
            "search_space_version": space.search_space_version,
            "constraint_satisfaction_probability": constraint_probability,
            "overall_feasibility_probability": overall_probability,
            "constraint_version": task_spec.get("constraint_version", ConstraintEvaluator.FORMULA_VERSION),
        }

    def _legal_fallback(self, space: Any, seed: int) -> dict[str, Any] | None:
        rng = np.random.default_rng(seed)
        for _ in range(512):
            raw = {}
            for name, spec in space.variables.items():
                if spec["type"] == "categorical":
                    raw[name] = spec["allowed_values"][int(rng.integers(len(spec["allowed_values"])))]
                elif spec["type"] == "integer":
                    raw[name] = int(rng.integers(math.ceil(spec["lower"]), math.floor(spec["upper"]) + 1))
                else:
                    raw[name] = float(rng.uniform(spec["lower"], spec["upper"]))
            candidate = project_candidate(raw, space)
            if self.constraints.all_satisfied(candidate, space.derived_constraints):
                return candidate
        return None


def _matches_fixed(raw: BOSample | dict[str, Any], fixed: dict[str, Any]) -> bool:
    parameters = raw.x_parameters if isinstance(raw, BOSample) else raw.get("x_parameters") or raw.get("x_parameters_json") or {}
    if isinstance(parameters, str):
        import json
        parameters = json.loads(parameters)
    for name, value in fixed.items():
        observed = parameters.get(name)
        if observed is None:
            return False
        if isinstance(value, (int, float)) and isinstance(observed, (int, float)):
            if not math.isclose(float(value), float(observed), rel_tol=1e-6, abs_tol=1e-9):
                return False
        elif value != observed:
            return False
    return True


def _prediction_map(result: dict[str, Any]) -> dict[str, dict[str, float]]:
    prediction = result.get("predictions") or {}
    metric = prediction.get("metric")
    mean = prediction.get("mean")
    std = prediction.get("uncertainty")
    return {metric: {"mean": mean, "std": std}} if metric and mean is not None and std is not None else {}
