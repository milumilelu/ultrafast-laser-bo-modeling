from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateChatSessionRequest(BaseModel):
    title: str | None = None
    mode: str = "agent"


class CreateChatSessionResponse(BaseModel):
    session_id: str
    title: str
    mode: str
    created_at: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    message: str
    mode: str = "agent"
    stream: bool = False


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    selected_skill: str | None = None
    route_plan: dict[str, Any] | None = None
    evidence_gap: dict[str, Any] | None = None
    knowledge_bootstrap: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    thinking_status: list[dict[str, Any]] = Field(default_factory=list)
    workflow_state: dict[str, Any] | None = None
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[Any] = Field(default_factory=list)
    audit_trace: list[dict[str, Any]] = Field(default_factory=list)
    rag_evidence: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    workflow_overview: list[dict[str, Any]] = Field(default_factory=list)
    current_stage: str | None = None
    current_stage_code: str | None = None
    completed_stages: list[str] = Field(default_factory=list)
    pending_stages: list[str] = Field(default_factory=list)
    blocked_stages: list[str] = Field(default_factory=list)
    next_required_action: dict[str, Any] = Field(default_factory=dict)
    skill_trace: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)


class ChatMessageView(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
