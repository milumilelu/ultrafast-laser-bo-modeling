from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewActionRequest(BaseModel):
    action: str
    reviewer_id: str
    comment: str = ""
    target_level: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
