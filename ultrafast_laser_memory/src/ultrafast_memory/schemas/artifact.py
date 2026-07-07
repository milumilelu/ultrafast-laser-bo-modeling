from __future__ import annotations

from pydantic import BaseModel


class ArtifactSchema(BaseModel):
    artifact_id: str
    file_path: str
    sha256: str
