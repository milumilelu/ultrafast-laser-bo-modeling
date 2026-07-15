from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ultrafast_domain.process import ParameterValue


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


class ParameterCandidate(BaseModel):
    """Open candidate metadata with strict per-parameter provenance."""

    model_config = ConfigDict(extra="allow")

    parameters: dict[str, ParameterValue] = Field(min_length=1)


class TrialPlan(BaseModel):
    """Open trial semantics: why, how, parameters, evaluation, and adaptation."""

    model_config = ConfigDict(extra="allow")

    objective: str
    hypothesis: str | None = None
    setup: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any]
    parameter_candidates: list[ParameterCandidate] = Field(min_length=1)
    evaluation_plan: list[dict[str, Any]] = Field(min_length=1)
    success_criteria: list[dict[str, Any]]
    stop_conditions: list[dict[str, Any]] = Field(default_factory=list)
    adaptation_guidance: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("setup", "strategy", mode="before")
    @classmethod
    def _normalize_open_object(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            return {"description": value.strip()}
        return value

    @field_validator("parameter_candidates", mode="before")
    @classmethod
    def _normalize_candidates(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value

    @field_validator(
        "evaluation_plan",
        "success_criteria",
        "stop_conditions",
        "adaptation_guidance",
        "provenance",
        mode="before",
    )
    @classmethod
    def _normalize_open_records(cls, value: Any) -> Any:
        if isinstance(value, (dict, str)):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return value
        return [
            {"description": item.strip()} if isinstance(item, str) and item.strip() else item
            for item in value
        ]

    @field_validator("warnings", mode="before")
    @classmethod
    def _normalize_warnings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value
