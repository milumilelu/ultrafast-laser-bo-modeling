from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


GeometryValidator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DomainPack:
    name: str
    component_types: tuple[str, ...]
    quality_metrics: tuple[str, ...]
    process_constraints: tuple[str, ...]
    trial_templates: dict[str, dict[str, Any]]
    measurement_templates: dict[str, dict[str, Any]]
    geometry_validator: GeometryValidator | None = None
    prompts: dict[str, str] = field(default_factory=dict)

    def validate_geometry(self, geometry: dict[str, Any]) -> dict[str, Any]:
        if self.geometry_validator is None:
            return {"valid": True, "missing_fields": [], "warnings": []}
        return self.geometry_validator(geometry)
