from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TrialAssessRequest(BaseModel):
    task_spec: dict[str, Any] = Field(default_factory=dict)
    evidence_status: str = "insufficient"
    approved_prior_count: int = 0
    similar_case_count: int = 0
    valid_sample_count: int = 0
    equipment_revision_unchanged: bool = False


class TrialSelectRequest(BaseModel):
    assessment: dict[str, Any]
    trial_mode: str


class TrialPlanCreateRequest(BaseModel):
    task_spec: dict[str, Any] = Field(default_factory=dict)
    trial_mode: str
    machine_bounds: dict[str, list[float | int]] = Field(default_factory=dict)
    domain_pack: str | None = None


class TrialExecutionCreateRequest(BaseModel):
    equipment_revision: str
    actual_parameters: dict[str, Any] = Field(default_factory=dict)
    actual_path: dict[str, Any] = Field(default_factory=dict)
    monitoring_summary: dict[str, Any] = Field(default_factory=dict)


class TrialResultCreateRequest(BaseModel):
    measurements: dict[str, Any] = Field(default_factory=dict)
    defects: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)


class TrialEvaluateRequest(BaseModel):
    reviewer_comment: str | None = None
    confirm_conditional: bool = False
