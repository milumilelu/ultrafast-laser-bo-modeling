from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlockedTool(BaseModel):
    tool: str
    reason: str


class StateUpdate(BaseModel):
    active_workflow: str | None = None
    active_skill: str | None = None
    workflow_stage: str | None = None
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    pending_questions: list[str] = Field(default_factory=list)
    allowed_next_skills: list[str] = Field(default_factory=list)


class RoutePlan(BaseModel):
    route_type: str = "agent_workflow"
    primary_skill: str
    secondary_skills: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    workflow_stage: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    requires_clarification: bool = False
    requires_internal_rag: bool = False
    requires_evidence_gap_check: bool = False
    requires_web_bootstrap: bool = False
    requires_user_permission: bool = False
    requires_expert_review: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    blocked_tools: list[BlockedTool] = Field(default_factory=list)
    state_update: StateUpdate = Field(default_factory=StateUpdate)
    route_source: str = "unknown"
    deprecated_skill_used: bool = False
    replacement_skill: str | None = None
    emitted_events: list[str] = Field(default_factory=list)


def fallback_route(reason: str = "Router confidence is low; fallback to task intake.") -> RoutePlan:
    return RoutePlan(
        primary_skill="task_understanding",
        intent="task_understanding",
        workflow_stage="clarification",
        confidence=0.3,
        reason=reason,
        requires_clarification=True,
        route_source="fallback",
        state_update=StateUpdate(workflow_stage="agent_planning"),
    )
