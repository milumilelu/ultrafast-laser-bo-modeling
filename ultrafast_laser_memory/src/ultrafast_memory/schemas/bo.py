from __future__ import annotations

from pydantic import BaseModel


class BoTrainingSampleSchema(BaseModel):
    sample_id: str
    run_id: str
    valid_for_training: bool
