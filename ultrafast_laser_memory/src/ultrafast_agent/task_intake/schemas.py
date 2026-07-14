from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EXTRACTION_VERSION = "llm-task-intake-v1"

# This is a vocabulary, not a completeness gate.  Individual tools declare
# the fields they need for the action they perform.
ALLOWED_TASK_FIELDS = frozenset(
    {
        "material",
        "process_type",
        "thickness_mm",
        "quality_requirement",
        "efficiency_requirement",
        "objective",
        "auxiliary",
        "component_type",
        "focus_tracking",
        # Cutting geometry.
        "cut_length_mm",
        "contour_type",
        "layer_cut_allowed",
        # Hole-drilling geometry and quality.
        "hole_diameter_mm",
        "hole_depth_mm",
        "through_hole",
        "taper_requirement",
        "entrance_quality",
        "exit_quality",
    }
)

EXPECTED_ANSWER_TYPES = {
    "material": "material_name",
    "process_type": "process_enum",
    "thickness_mm": "length",
    "quality_requirement": "quality_requirement",
    "cut_length_mm": "length_with_contour",
    "efficiency_requirement": "efficiency_requirement",
    "objective": "optimization_objective",
    "auxiliary": "auxiliary_medium",
    "layer_cut_allowed": "boolean",
    "contour_type": "contour_enum",
    "hole_diameter_mm": "length",
    "hole_depth_mm": "length",
    "through_hole": "boolean",
    "taper_requirement": "quality_requirement",
    "entrance_quality": "quality_requirement",
    "exit_quality": "quality_requirement",
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
    schema_valid: bool | None = None
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
