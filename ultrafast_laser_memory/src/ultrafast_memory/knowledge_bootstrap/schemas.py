from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceGapRequest(BaseModel):
    task_spec: dict[str, Any] = Field(default_factory=dict)
    question: str
    internal_hits: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceGapResponse(BaseModel):
    has_sufficient_internal_evidence: bool
    evidence_score: float
    missing_evidence: list[str]
    recommended_action: str
    reason: str


class BootstrapWebRequest(BaseModel):
    task_spec: dict[str, Any] = Field(default_factory=dict)
    query_intent: str = "find_literature_prior"
    question: str | None = None
    max_sources: int = 5
    review_required: bool = True


class BootstrapWebResponse(BaseModel):
    sources: list[dict[str, Any]]
    knowledge_candidates: list[dict[str, Any]]
    review_tasks: list[dict[str, Any]]
    auto_indexed: list[dict[str, Any]] = Field(default_factory=list)
    requires_review: list[dict[str, Any]]
