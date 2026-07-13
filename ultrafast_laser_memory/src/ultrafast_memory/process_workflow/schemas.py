from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProcessState(StrEnum):
    CREATED = "CREATED"
    INTAKE = "INTAKE"
    REQUIREMENTS_PENDING = "REQUIREMENTS_PENDING"
    REQUIREMENTS_CONFIRMED = "REQUIREMENTS_CONFIRMED"
    EQUIPMENT_LOADING = "EQUIPMENT_LOADING"
    EVIDENCE_RETRIEVAL = "EVIDENCE_RETRIEVAL"
    EVIDENCE_ASSESSMENT = "EVIDENCE_ASSESSMENT"
    TRIAL_ASSESSMENT = "TRIAL_ASSESSMENT"
    TRIAL_MODE_PENDING = "TRIAL_MODE_PENDING"
    TRIAL_PLAN_READY = "TRIAL_PLAN_READY"
    TRIAL_EXECUTION_PENDING = "TRIAL_EXECUTION_PENDING"
    TRIAL_RESULT_PENDING = "TRIAL_RESULT_PENDING"
    TRIAL_RESULT_EVALUATION = "TRIAL_RESULT_EVALUATION"
    KNOWLEDGE_APPROVAL_PENDING = "KNOWLEDGE_APPROVAL_PENDING"
    BO_READY = "BO_READY"
    BO_RUNNING = "BO_RUNNING"
    FORMAL_PROCESS_READY = "FORMAL_PROCESS_READY"
    FORMAL_RELEASE_PENDING = "FORMAL_RELEASE_PENDING"
    FORMAL_PREFLIGHT = "FORMAL_PREFLIGHT"
    FORMAL_PROCESS_RUNNING = "FORMAL_PROCESS_RUNNING"
    FINAL_INSPECTION_PENDING = "FINAL_INSPECTION_PENDING"
    QUALITY_DECISION = "QUALITY_DECISION"
    REWORK_PENDING = "REWORK_PENDING"
    REPORT_PENDING = "REPORT_PENDING"
    ARCHIVE_PENDING = "ARCHIVE_PENDING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ParameterValue(BaseModel):
    name: str
    value: float | int | str | None = None
    range: list[float] | None = None
    unit: str
    source_type: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    allowed_for_simple_trial: bool = False
    allowed_for_full_trial: bool = False
    allowed_for_formal_process: bool = False
    allowed_for_bo_prior: bool = False

    @model_validator(mode="after")
    def reject_free_form(self):
        if self.source_type == "free_form_llm_estimate":
            if any((self.allowed_for_simple_trial, self.allowed_for_full_trial,
                    self.allowed_for_formal_process, self.allowed_for_bo_prior)):
                raise ValueError("free_form_llm_estimate is forbidden for every use")
        return self


class ParameterRecommendation(BaseModel):
    recommendation_id: str
    recommendation_mode: Literal["bo", "bo_with_rag_prior", "rag", "llm_fallback", "blocked"]
    support_status: Literal["supported", "partially_supported", "insufficient"]
    authority_level: Literal["verified", "reviewed", "evidence_based", "exploratory", "none"]
    intended_use: Literal["simple_trial", "full_trial", "formal_process", "bo_prior"]
    parameters: list[ParameterValue] = Field(default_factory=list)
    context_match: dict[str, Any] = Field(default_factory=dict)
    data_support: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    constraints_applied: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_review: bool = False
    requires_trial_validation: bool = True


class NextAction(BaseModel):
    action_type: str
    title: str
    required_fields: list[dict[str, Any]] = Field(default_factory=list)
    allowed_values: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    blocking: bool = True


class WorkflowProgress(BaseModel):
    workflow_overview: list[dict[str, Any]]
    current_stage: str
    completed_stages: list[str]
    pending_stages: list[str]
    blocked_stages: list[str] = Field(default_factory=list)
    next_required_action: NextAction
    completed_steps: int
    total_steps: int
    percent: int


class ReasoningTrace(BaseModel):
    trace_id: str
    sequence: int
    stage: str
    event_type: str
    title: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    alternatives_considered: list[dict[str, Any]] = Field(default_factory=list)
    selected_alternative: str | None = None
    rejection_reasons: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None
    visibility: Literal["public"] = "public"
    created_at: str


class CampaignState(StrEnum):
    CAMPAIGN_CREATED = "CAMPAIGN_CREATED"
    ITERATION_PLANNING = "ITERATION_PLANNING"
    DATA_SUPPORT_ASSESSMENT = "DATA_SUPPORT_ASSESSMENT"
    PARAMETER_SOURCE_SELECTION = "PARAMETER_SOURCE_SELECTION"
    CANDIDATE_GENERATION = "CANDIDATE_GENERATION"
    CANDIDATE_FILTERING = "CANDIDATE_FILTERING"
    CANDIDATE_APPROVAL_PENDING = "CANDIDATE_APPROVAL_PENDING"
    ITERATION_EXECUTION = "ITERATION_EXECUTION"
    OBSERVATION_PENDING = "OBSERVATION_PENDING"
    OBSERVATION_VALIDATION = "OBSERVATION_VALIDATION"
    MODEL_UPDATE = "MODEL_UPDATE"
    ITERATION_DECISION = "ITERATION_DECISION"
    CAMPAIGN_CONVERGED = "CAMPAIGN_CONVERGED"
    CAMPAIGN_BUDGET_EXHAUSTED = "CAMPAIGN_BUDGET_EXHAUSTED"
    CAMPAIGN_BLOCKED = "CAMPAIGN_BLOCKED"
    CAMPAIGN_TERMINATED = "CAMPAIGN_TERMINATED"


class OptimizationCampaign(BaseModel):
    campaign_id: str
    task_id: str
    campaign_type: Literal["simple_trial_campaign", "full_trial_campaign", "formal_process_campaign", "rework_campaign"]
    fidelity_level: Literal["simple_trial", "full_trial", "formal_process", "rework"]
    material_context: dict[str, Any]
    equipment_revision: str
    active_variables: list[str]
    fixed_parameters: dict[str, Any] = Field(default_factory=dict)
    objectives: list[dict[str, Any]]
    hard_constraints: list[dict[str, Any]]
    soft_constraints: list[dict[str, Any]] = Field(default_factory=list)
    search_space: dict[str, Any]
    budget: dict[str, Any]
    current_iteration: int = 0
    status: CampaignState = CampaignState.CAMPAIGN_CREATED
