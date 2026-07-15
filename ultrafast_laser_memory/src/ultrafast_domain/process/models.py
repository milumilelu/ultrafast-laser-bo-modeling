from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ParameterRole = Literal[
    "equipment_fixed",
    "process_setpoint",
    "strategy_parameter",
    "derived_metric",
]


class ParameterValue(BaseModel):
    """One provenance-bearing value; equipment capability ranges use a separate contract."""

    model_config = ConfigDict(extra="allow")

    name: str
    value: float | int | str
    unit: str | None = None
    role: ParameterRole
    source_type: str
    source_refs: list[str] = Field(default_factory=list)
    authority_level: str
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    validated: bool = False
    allowed_for_trial: bool = False
    allowed_for_formal_process: bool = False
    allowed_for_bo_training: bool = False


class ProcessPlan(BaseModel):
    """Open semantic plan; concrete strategy fields are selected per task by the Main Agent."""

    model_config = ConfigDict(extra="allow")

    objective: str
    strategy: dict[str, Any]
    operations: list[dict[str, Any]]
    fixed_conditions: dict[str, Any] = Field(default_factory=dict)
    controllable_variables: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_plan: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    adaptation_guidance: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("strategy", mode="before")
    @classmethod
    def _normalize_strategy(cls, value: Any) -> Any:
        """Accept concise natural-language strategy while storing an open object."""
        if isinstance(value, str) and value.strip():
            return {"description": value.strip()}
        return value

    @field_validator(
        "operations",
        "controllable_variables",
        "evaluation_plan",
        "risks",
        "adaptation_guidance",
        mode="before",
    )
    @classmethod
    def _normalize_open_records(cls, value: Any) -> Any:
        """Canonicalize equivalent record shapes without adding task-specific fields."""
        if isinstance(value, (dict, str)):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return value
        return [
            {"description": item.strip()} if isinstance(item, str) and item.strip() else item
            for item in value
        ]
