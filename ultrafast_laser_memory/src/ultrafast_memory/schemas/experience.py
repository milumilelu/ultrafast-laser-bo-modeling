from __future__ import annotations

from pydantic import BaseModel


class ExperienceCandidateSchema(BaseModel):
    candidate_id: str
    extracted_claim: str
    status: str
