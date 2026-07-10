from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BOModelStatus(StrEnum):
    RULE_BASED_COLD_START = "rule_based_cold_start"
    HYBRID_RULE_BO = "hybrid_rule_bo"
    DATA_DRIVEN_BO = "data_driven_bo"
    BLOCKED = "blocked"


@dataclass(slots=True)
class BOSample:
    sample_id: str
    x_parameters: dict[str, float]
    y_metrics: dict[str, float]
    valid_for_training: bool = True
    material: str | None = None
    process_type: str | None = None


@dataclass(slots=True)
class BORecommendation:
    model_status: str
    sample_count: int
    recommended_parameters: dict[str, float | int]
    prediction: dict[str, float | None]
    acquisition: dict[str, Any]
    bo_invoked: bool
    machine_bounds_revision: str | None = None
    knowledge_approval_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    audit_trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
