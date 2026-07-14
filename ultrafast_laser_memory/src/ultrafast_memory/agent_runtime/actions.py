from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    """The only wire-level action contract accepted by the main Agent loop."""

    action: Literal["load_skill", "unload_skill", "call_tool", "ask_user", "final_answer"]
    decision_summary: str
    skill_name: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    provider: str | None = None
    model: str | None = None
    error_details: list[dict[str, str]] = Field(default_factory=list)
