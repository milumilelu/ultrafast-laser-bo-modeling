from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeUseEvaluateRequest(BaseModel):
    session_id: str | None = None
    task_spec: dict[str, Any] = Field(default_factory=dict)
    intended_use: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    equipment: dict[str, Any] = Field(default_factory=dict)
    proposed_usage: dict[str, Any] = Field(default_factory=dict)


class KnowledgeUseActionRequest(BaseModel):
    reviewer_id: str
    comment: str | None = None
    approved_payload: dict[str, Any] = Field(default_factory=dict)


class KnowledgeApprovalRevokeRequest(BaseModel):
    reviewer_id: str
    comment: str | None = None
