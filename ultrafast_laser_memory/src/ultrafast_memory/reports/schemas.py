from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskReportGenerateRequest(BaseModel):
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
