from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TrialMode(StrEnum):
    SKIP = "skip_trial"
    SIMPLE = "simple_trial_cut"
    FULL = "full_trial_cut"


class TrialDecision(StrEnum):
    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class TrialAssessment:
    recommended_mode: TrialMode
    allowed_modes: tuple[TrialMode, ...]
    reasons: tuple[str, ...]
    risk_level: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_mode": self.recommended_mode.value,
            "allowed_modes": [mode.value for mode in self.allowed_modes],
            "reasons": list(self.reasons),
            "risk_level": self.risk_level,
        }


@dataclass(slots=True)
class TrialPlanDraft:
    task_id: str
    trial_mode: TrialMode
    representative_geometry: dict[str, Any]
    parameter_matrix: list[dict[str, float | int]]
    measurement_plan: dict[str, Any]
    acceptance_criteria: list[dict[str, Any]]
    stop_conditions: list[dict[str, Any]]
    status: str = "draft"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trial_mode"] = self.trial_mode.value
        return value
