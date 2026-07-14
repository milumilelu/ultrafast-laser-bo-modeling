from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DOCUMENT_ELEMENT_TYPES = frozenset(
    {"title", "paragraph", "table", "table_cell", "caption", "header", "footer", "formula_text", "unknown"}
)


@dataclass(frozen=True, slots=True)
class DocumentElement:
    document_id: str
    page_number: int
    element_id: str
    element_type: str
    content: str
    bbox: tuple[float, float, float, float] | None
    confidence: float | None
    parser_name: str
    parser_version: str
    source_image_hash: str
    review_status: str = "unreviewed"

    def __post_init__(self) -> None:
        if self.element_type not in DOCUMENT_ELEMENT_TYPES:
            raise ValueError(f"unsupported document element type: {self.element_type}")
        if self.page_number < 1:
            raise ValueError("page number must be positive")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["bbox"] = list(self.bbox) if self.bbox else None
        return value


@dataclass(frozen=True, slots=True)
class OcrDocument:
    document_id: str
    artifact_id: str
    parser_name: str
    parser_version: str
    source_hash: str
    elements: tuple[DocumentElement, ...]
    failed_pages: tuple[int, ...] = ()
    review_status: str = "unreviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id, "artifact_id": self.artifact_id,
            "parser_name": self.parser_name, "parser_version": self.parser_version,
            "source_hash": self.source_hash, "elements": [value.to_dict() for value in self.elements],
            "failed_pages": list(self.failed_pages), "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class VisionAnalysisCandidate:
    analysis_id: str
    artifact_id: str
    analysis_type: str
    observations: tuple[dict[str, Any], ...]
    regions: tuple[dict[str, Any], ...]
    confidence: float | None
    limitations: tuple[str, ...]
    provider: str
    model: str
    prompt_version: str
    status: str = "experimental_unvalidated"
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for name in ("observations", "regions", "limitations"):
            value[name] = list(value[name])
        return value
