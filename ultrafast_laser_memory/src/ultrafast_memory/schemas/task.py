from __future__ import annotations

from pydantic import BaseModel


class TaskSchema(BaseModel):
    task_id: str
    material: str | None = None
