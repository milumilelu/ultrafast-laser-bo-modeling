from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EXTRACTION_VERSION = "llm-task-intake-v1"

PROCESS_REQUIRED_FIELDS = (
    "material",
    "process_type",
    "thickness_mm",
    "quality_requirement",
    "cut_length_mm",
    "efficiency_requirement",
    "auxiliary",
    "layer_cut_allowed",
)

ALLOWED_TASK_FIELDS = frozenset(
    {
        *PROCESS_REQUIRED_FIELDS,
        "contour_type",
        "focus_tracking",
        "component_type",
    }
)

EXPECTED_ANSWER_TYPES = {
    "material": "material_name",
    "process_type": "process_enum",
    "thickness_mm": "length",
    "quality_requirement": "quality_requirement",
    "cut_length_mm": "length_with_contour",
    "efficiency_requirement": "efficiency_requirement",
    "auxiliary": "auxiliary_medium",
    "layer_cut_allowed": "boolean",
    "contour_type": "contour_enum",
}


class ClarificationContext(BaseModel):
    workflow_type: str
    stage: str
    clarification_round: int = 0
    pending_fields: list[str] = Field(default_factory=list)
    ordered_fields: list[str] = Field(default_factory=list)
    previous_questions: list[dict[str, Any]] = Field(default_factory=list)
    expected_answer_types: dict[str, str] = Field(default_factory=dict)


class TaskFieldCandidate(BaseModel):
    field_name: str
    raw_value: Any
    normalized_value: Any | None = None
    unit: str | None = None
    evidence: str
    extraction_source: str
    confidence: float = Field(ge=0, le=1)
    operation: Literal["fill", "correct"] = "fill"
    ambiguity: str | None = None


class TaskSpecPatch(BaseModel):
    updates: list[TaskFieldCandidate] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    extraction_version: str = EXTRACTION_VERSION
    llm_attempted: bool = False
    degraded: bool = False
    provider: str | None = None
    model: str | None = None
    extraction_mode: Literal["llm_structured", "strict_key_value", "not_run"] = "llm_structured"
    attempt_count: int = 0

    @property
    def extractor_version(self) -> str:
        return self.extraction_version


class MergeResult(BaseModel):
    task_spec: dict[str, Any]
    field_provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)
    revision_history: list[dict[str, Any]] = Field(default_factory=list)
    applied: list[TaskFieldCandidate] = Field(default_factory=list)
    unchanged: list[TaskFieldCandidate] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
