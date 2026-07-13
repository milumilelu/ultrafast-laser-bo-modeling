from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
import uuid

from ultrafast_domain.documents import VisionAnalysisCandidate


class VisionSemanticProvider(ABC):
    @abstractmethod
    def analyze(self, image_artifact: dict[str, Any], analysis_type: str, context: dict[str, Any]) -> VisionAnalysisCandidate: ...


class MultimodalLLMVisionProvider(VisionSemanticProvider):
    """Experimental adapter skeleton. It is deliberately absent from API/tool registries."""

    def __init__(self, client: Any | None = None, *, enabled: bool = False, model: str = "unconfigured", prompt_version: str = "vision-stub-1.0"):
        self.client = client
        self.enabled = enabled
        self.model = model
        self.prompt_version = prompt_version

    def analyze(self, image_artifact: dict[str, Any], analysis_type: str, context: dict[str, Any]) -> VisionAnalysisCandidate:
        if not self.enabled:
            error = RuntimeError("vision semantic analysis is disabled")
            error.code = "experimental_disabled"  # type: ignore[attr-defined]
            raise error
        if self.client is None:
            error = RuntimeError("multimodal provider is unavailable")
            error.code = "provider_unavailable"  # type: ignore[attr-defined]
            raise error
        raw = self.client.analyze_image(image_artifact=image_artifact, analysis_type=analysis_type, context=context)
        return VisionAnalysisCandidate(
            analysis_id=f"vision_analysis_{uuid.uuid4().hex}", artifact_id=str(image_artifact["artifact_id"]),
            analysis_type=analysis_type, observations=tuple(raw.get("observations") or ()),
            regions=tuple(raw.get("regions") or ()), confidence=raw.get("confidence"),
            limitations=tuple(raw.get("limitations") or ("experimental result; human validation required",)),
            provider=str(raw.get("provider") or "multimodal_llm"), model=self.model,
            prompt_version=self.prompt_version, status="experimental_unvalidated",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

