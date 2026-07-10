from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    material: str | None = None
    material_grade: str | None = None
    component_type: str | None = None
    process_type: str | None = None
    geometry: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    revision: int = 1

    def missing_fields(self) -> list[str]:
        return [
            name
            for name in ("material", "component_type", "process_type")
            if not getattr(self, name)
        ]

    def revise(self, **changes: Any) -> "TaskSpec":
        values = {
            "task_id": self.task_id,
            "material": self.material,
            "material_grade": self.material_grade,
            "component_type": self.component_type,
            "process_type": self.process_type,
            "geometry": dict(self.geometry),
            "targets": dict(self.targets),
            "constraints": dict(self.constraints),
            "revision": self.revision + 1,
        }
        values.update(changes)
        return TaskSpec(**values)
