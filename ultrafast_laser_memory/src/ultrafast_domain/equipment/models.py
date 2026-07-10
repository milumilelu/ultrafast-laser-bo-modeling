from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EquipmentSnapshot:
    profile_id: str
    revision_id: str
    machine_bounds: dict[str, list[float]]
    capabilities: dict[str, Any] = field(default_factory=dict)

    def contains(self, parameters: dict[str, float | int]) -> bool:
        for name, value in parameters.items():
            if name not in self.machine_bounds:
                continue
            lower, upper = self.machine_bounds[name]
            if float(value) < float(lower) or float(value) > float(upper):
                return False
        return True
