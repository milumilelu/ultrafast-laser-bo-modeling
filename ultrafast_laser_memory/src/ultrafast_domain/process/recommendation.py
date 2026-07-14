from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


RECOMMENDATION_STAGES = frozenset(
    {"trial_cut", "production_candidate", "production_approved", "reoptimization", "manual_override"}
)
RECOMMENDATION_STATUSES = frozenset(
    {"ready_for_trial", "ready_for_cam", "pending_review", "blocked", "expired", "superseded"}
)


@dataclass(frozen=True, slots=True)
class ProcessRecommendation:
    recommendation_id: str
    task_id: str
    workflow_id: str
    iteration_number: int
    parent_recommendation_id: str | None
    process_type: str
    material: str
    component_type: str | None
    stage: str
    complete_recipe: dict[str, Any]
    parameter_metadata: dict[str, dict[str, Any]]
    optimized_parameters: dict[str, Any]
    fixed_parameters: dict[str, Any]
    forbidden_parameters: dict[str, str]
    predictions: dict[str, Any]
    constraints: dict[str, Any]
    recommendation_source: str
    source_run_id: str | None
    confidence: dict[str, Any]
    model_version: str | None
    dataset_version: str | None
    search_space_version: str
    objective_version: str
    constraint_version: str
    evidence_ids: tuple[str, ...] = ()
    prior_ids: tuple[str, ...] = ()
    status: str = "pending_review"
    created_at: str | None = None
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in RECOMMENDATION_STAGES:
            raise ValueError(f"unsupported recommendation stage: {self.stage}")
        if self.status not in RECOMMENDATION_STATUSES:
            raise ValueError(f"unsupported recommendation status: {self.status}")
        if self.iteration_number < 1:
            raise ValueError("iteration number must be positive")
        if self.stage == "production_approved" and self.recommendation_source == "llm_trial_fallback":
            raise ValueError("LLM trial fallback cannot become production approved")
        overlap = set(self.optimized_parameters) & set(self.fixed_parameters)
        if overlap:
            raise ValueError(f"parameters cannot be both optimized and fixed: {sorted(overlap)}")
        expected = set(self.optimized_parameters) | set(self.fixed_parameters)
        if not expected.issubset(self.complete_recipe):
            raise ValueError("complete recipe is missing optimized or fixed parameters")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence_ids"] = list(self.evidence_ids)
        value["prior_ids"] = list(self.prior_ids)
        return value
