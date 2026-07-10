from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProcessPlan:
    task_id: str
    route: list[str] = field(default_factory=list)
    parameter_window: dict[str, list[float]] = field(default_factory=dict)
    quality_plan: dict[str, Any] = field(default_factory=dict)
    stop_conditions: list[dict[str, Any]] = field(default_factory=list)
    status: str = "draft"
