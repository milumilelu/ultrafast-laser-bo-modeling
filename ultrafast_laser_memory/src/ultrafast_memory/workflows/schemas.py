from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowExecuteRequest(BaseModel):
    task_id: str
    session_id: str | None = None
    task_spec: dict[str, Any] = Field(default_factory=dict)
    equipment_snapshot: dict[str, Any] | None = None
    question: str | None = None
    selected_trial_mode: str | None = None
    intended_use: str = "parameter_recommendation"
    context: dict[str, Any] = Field(default_factory=dict)
    display_mode: str = "normal"
