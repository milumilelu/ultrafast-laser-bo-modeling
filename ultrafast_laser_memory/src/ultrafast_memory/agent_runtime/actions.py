from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ACTION_SCHEMA_VERSION = "v31-minimal-action-1"


class AgentAction(BaseModel):
    """The only wire-level action contract accepted by the main Agent loop."""

    action: Literal["update_context", "call_tool", "ask_user", "respond"]
    decision_summary: str
    skills_used: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    context_updates: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    error_details: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_payload_for_action(self) -> AgentAction:
        if self.action == "call_tool" and not self.tool_name:
            raise ValueError("tool_name_required")
        if self.action in {"ask_user", "respond"} and not self.message:
            raise ValueError("message_required")
        if self.action == "update_context" and not self.context_updates:
            raise ValueError("context_updates_required")
        return self
