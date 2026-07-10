from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = 8
    purpose: str = "literature_background"
    index_name: str = "literature_default"
    session_id: str | None = None


class EvidenceHit(BaseModel):
    chunk_id: str
    paper_id: str
    title: str = ""
    authors: str = ""
    year: str = ""
    doi: str = ""
    page_start: int
    page_end: int
    section_type: str = "unknown"
    content: str
    score: float
    scenario_id: str = ""
    material: str = ""
    process_type: str = ""
    evidence_level: str = ""
    review_status: str = ""
    usable_for: list[str] = Field(default_factory=list)
    not_usable_for: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    evidence_status: str
    hits: list[EvidenceHit] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
