from __future__ import annotations

from pydantic import BaseModel


class RunSchema(BaseModel):
    run_id: str
    run_status: str | None = None
