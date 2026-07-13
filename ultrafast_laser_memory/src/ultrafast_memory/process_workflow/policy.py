from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ultrafast_memory.core.ids import stable_id

from .schemas import ParameterRecommendation, ParameterValue


Tool = Callable[[dict[str, Any]], ParameterRecommendation]


class ParameterRecommendationPolicy:
    """BO-first policy. This class chooses tools; it never invents parameters."""

    def __init__(self, bo_tool: Tool, rag_tool: Tool, llm_fallback_tool: Tool | None = None,
                 validator: Callable[[ParameterRecommendation, dict[str, Any]], ParameterRecommendation] | None = None):
        self.bo_tool, self.rag_tool = bo_tool, rag_tool
        self.llm_fallback_tool, self.validator = llm_fallback_tool, validator
        self.call_order: list[str] = []

    def recommend(self, context: dict[str, Any]) -> ParameterRecommendation:
        self.call_order = ["bo_parameter_recommendation_tool"]
        bo = self.bo_tool(context)
        if bo.support_status == "supported":
            return self._validate(bo, context)
        if bo.support_status == "partially_supported":
            self.call_order.append("rag_parameter_recommendation_tool")
            prior = self.rag_tool({**context, "intended_use": "bo_prior"})
            if prior.support_status == "supported" and not prior.requires_review:
                self.call_order.append("bo_parameter_recommendation_tool")
                return self._validate(self.bo_tool({**context, "approved_priors": prior.model_dump()}), context)
        self.call_order.append("rag_parameter_recommendation_tool")
        rag = self.rag_tool({**context, "intended_use": "simple_trial"})
        if rag.support_status == "supported":
            return self._validate(rag, context)
        if rag.support_status == "partially_supported":
            rag.requires_review = True
            rag.warnings.append("aggregated review required before use")
            return rag
        if not self._fallback_allowed(context) or self.llm_fallback_tool is None:
            return ParameterRecommendation(
                recommendation_id=stable_id("rec", "blocked", str(context.get("task_id"))),
                recommendation_mode="blocked", support_status="insufficient",
                authority_level="none", intended_use="simple_trial",
                warnings=["BO and RAG evidence are insufficient; fallback is not authorized"],
            )
        self.call_order.append("llm_fallback_parameter_tool")
        result = self.llm_fallback_tool({**context, "intended_use": "simple_trial"})
        result.recommendation_mode = "llm_fallback"
        result.authority_level = "exploratory"
        result.intended_use = "simple_trial"
        result.requires_review = True
        result.requires_trial_validation = True
        for parameter in result.parameters:
            parameter.source_type = "llm_fallback_hypothesis"
            parameter.allowed_for_simple_trial = True
            parameter.allowed_for_full_trial = False
            parameter.allowed_for_formal_process = False
            parameter.allowed_for_bo_prior = False
        return self._validate(result, context)

    def _fallback_allowed(self, context: dict[str, Any]) -> bool:
        return all((context.get("allow_llm_fallback"), context.get("user_allows_exploration"),
                    context.get("trial_allowed"), context.get("equipment_hard_bounds_complete")))

    def _validate(self, result: ParameterRecommendation, context: dict[str, Any]):
        return self.validator(result, context) if self.validator else result


def validate_parameter_constraints(result: ParameterRecommendation, context: dict[str, Any]) -> ParameterRecommendation:
    bounds = context.get("equipment_bounds") or {}
    intended = result.intended_use
    valid: list[ParameterValue] = []
    for parameter in result.parameters:
        bound = bounds.get(parameter.name)
        if bound and parameter.value is not None and isinstance(parameter.value, (int, float)):
            if isinstance(bound, (list, tuple)) and len(bound) == 2:
                low, high = bound
            else:
                low, high = bound.get("min"), bound.get("max")
            if (low is not None and parameter.value < low) or (high is not None and parameter.value > high):
                result.warnings.append(f"{parameter.name} rejected: outside equipment bounds")
                continue
        permitted = {
            "simple_trial": parameter.allowed_for_simple_trial,
            "full_trial": parameter.allowed_for_full_trial,
            "formal_process": parameter.allowed_for_formal_process,
            "bo_prior": parameter.allowed_for_bo_prior,
        }[intended]
        if not permitted:
            result.warnings.append(f"{parameter.name} rejected: source not permitted for {intended}")
            continue
        valid.append(parameter)
    result.parameters = valid
    result.constraints_applied.extend(["unit_validation", "equipment_hard_bounds", "source_authority", "intended_use"])
    return result


def formal_release_gate(*, trial_passed: bool, source_types: list[str], equipment_revision_matches: bool,
                        preflight_complete: bool) -> tuple[bool, list[str]]:
    reasons = []
    allowed_sources = {"verified_experiment", "bo_recommendation", "bo_recommendation_with_rag_prior"}
    if not trial_passed:
        reasons.append("trial_not_passed")
    if not source_types or any(source not in allowed_sources for source in source_types):
        reasons.append("illegal_parameter_source")
    if not equipment_revision_matches:
        reasons.append("equipment_revision_changed")
    if not preflight_complete:
        reasons.append("preflight_incomplete")
    return not reasons, reasons
