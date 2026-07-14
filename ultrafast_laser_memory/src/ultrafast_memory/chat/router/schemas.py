from __future__ import annotations

from pydantic import BaseModel, Field


class RoutePlan(BaseModel):
    """Non-binding capability hints; never a workflow or permission controller."""

    route_type: str = "agent_workflow"
    primary_skill: str
    secondary_skills: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    workflow_stage: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    route_source: str = "unknown"


def fallback_route(reason: str = "Router confidence is low; fallback to task intake.") -> RoutePlan:
    return RoutePlan(
        primary_skill="task_understanding",
        intent="task_understanding",
        workflow_stage="agent_planning",
        confidence=0.3,
        reason=reason,
        route_source="fallback",
    )
