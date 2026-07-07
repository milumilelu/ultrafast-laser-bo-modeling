from __future__ import annotations

from pydantic import BaseModel


class RecipeSchema(BaseModel):
    recipe_id: str
    task_id: str | None = None
