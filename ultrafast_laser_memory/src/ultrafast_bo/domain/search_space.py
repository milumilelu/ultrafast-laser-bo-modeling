from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ParameterMode(StrEnum):
    FIXED = "fixed"
    OPTIMIZABLE = "optimizable"
    BOUNDED = "bounded"
    INTEGER = "integer"
    CATEGORICAL = "categorical"
    CONDITIONAL = "conditional"
    DERIVED = "derived"
    FORBIDDEN = "forbidden"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ParameterPolicy:
    mode: str
    value: Any = None
    lower: float | None = None
    upper: float | None = None
    step: float | None = None
    allowed_values: tuple[Any, ...] = ()
    condition: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    unit: str | None = None

    @classmethod
    def from_value(cls, value: "ParameterPolicy | dict[str, Any]") -> "ParameterPolicy":
        if isinstance(value, cls):
            return value
        data = dict(value)
        if isinstance(data.get("allowed_values"), list):
            data["allowed_values"] = tuple(data["allowed_values"])
        return cls(**data)


@dataclass(slots=True)
class CompiledSearchSpace:
    variables: dict[str, dict[str, Any]]
    fixed_parameters: dict[str, Any]
    forbidden_parameters: dict[str, str]
    derived_constraints: list[dict[str, Any]]
    outcome_constraints: list[dict[str, Any]]
    source_trace: list[dict[str, Any]]
    search_space_version: str
    feasibility_status: str
    blocking_reasons: list[str]
    conflicting_sources: list[dict[str, Any]]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

