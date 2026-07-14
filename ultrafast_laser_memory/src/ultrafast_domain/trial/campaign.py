from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TrialStrategy(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    EXPLORATORY = "exploratory"


TRIAL_STRATEGY_POLICIES = {
    TrialStrategy.CONSERVATIVE: {
        "risk_posture": "lowest_risk",
        "search_width": 0.25,
        "iteration_budget": 2,
        "exploration_preference": 0.1,
    },
    TrialStrategy.BALANCED: {
        "risk_posture": "balanced",
        "search_width": 0.5,
        "iteration_budget": 3,
        "exploration_preference": 0.4,
    },
    TrialStrategy.EXPLORATORY: {
        "risk_posture": "review_required",
        "search_width": 0.8,
        "iteration_budget": 4,
        "exploration_preference": 0.75,
    },
}


class TrialDecision(StrEnum):
    CONTINUE_TRIAL = "CONTINUE_TRIAL"
    TRIAL_SUCCEEDED = "TRIAL_SUCCEEDED"
    TRIAL_BLOCKED = "TRIAL_BLOCKED"
    ESCALATE_REVIEW = "ESCALATE_REVIEW"


@dataclass(frozen=True, slots=True)
class TrialObservation:
    observation_id: str
    campaign_id: str
    iteration_id: str
    recommendation_id: str
    recommended_parameters: dict[str, Any]
    cam_applied_parameters: dict[str, Any]
    machine_actual_parameters: dict[str, Any]
    measurements: dict[str, Any]
    parameter_units: dict[str, str]
    measurement_units: dict[str, str]
    constraint_results: dict[str, bool]
    alarms: tuple[str, ...]
    risk_state: str
    eligibility_report: dict[str, Any]
    dataset_version: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TrialIteration:
    iteration_id: str
    campaign_id: str
    iteration_number: int
    recommendation_id: str
    parent_recommendation_id: str | None
    observation_id: str | None = None
    decision: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrialCampaign:
    campaign_id: str
    task_id: str
    workflow_id: str
    task_spec: dict[str, Any]
    search_space: dict[str, Any]
    current_recipe: dict[str, Any]
    parameter_units: dict[str, str]
    equipment_revision: str
    targets: dict[str, Any]
    constraints: dict[str, Any]
    business_state: str = "TRIAL"
    substatus: str = "TRIAL_STRATEGY_PENDING"
    strategy: str | None = None
    iteration_budget: int = 3
    current_iteration: int = 0
    production_candidate_id: str | None = None
    production_approved_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
