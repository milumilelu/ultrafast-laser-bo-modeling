from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


InventoryStatus = Literal[
    "discovered",
    "planned",
    "ingested",
    "skipped_duplicate",
    "needs_review",
    "needs_ocr",
    "failed",
]


class InventoryRecord(BaseModel):
    inventory_id: str
    path: str
    asset_type: str
    sha256: str
    file_size_bytes: int
    modified_at: str
    discovered_at: str
    ingestion_status: InventoryStatus = "discovered"
    related_root: str | None = None


class LiteratureCard(BaseModel):
    paper_id: str
    source_id: str | None = None
    title: str = ""
    authors: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    source: str = ""
    scenario_id: str = ""
    material: str = ""
    material_grade: str = ""
    component_type: str = ""
    process_type: str = ""
    laser_type: str = ""
    wavelength_nm: float | None = None
    pulse_width_fs: float | None = None
    power_or_energy: str = ""
    frequency_kHz: float | None = None
    scan_speed_mm_s: float | None = None
    beam_shape: str = ""
    environment: str = ""
    geometry: dict[str, Any] = Field(default_factory=dict)
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    defects: list[str] = Field(default_factory=list)
    measurement_methods: list[str] = Field(default_factory=list)
    mechanism_claims: list[str] = Field(default_factory=list)
    usable_for: list[str] = Field(default_factory=lambda: ["literature_background", "evidence_retrieval"])
    not_usable_for: list[str] = Field(default_factory=lambda: ["direct_parameter_recommendation", "BO_training"])
    evidence_level: str = "literature_evidence_candidate"
    review_status: str = "pending_review"
    notes: str = ""
    conflicts: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("doi", mode="before")
    @classmethod
    def normalize_doi_field(cls, value: Any) -> str:
        from ultrafast_memory.literature.canonicalizer import normalize_doi

        return normalize_doi(str(value or ""))

    @field_validator("year", mode="before")
    @classmethod
    def validate_year(cls, value: Any) -> str:
        text = str(value or "").strip()
        return text if not text or (len(text) == 4 and text.isdigit()) else ""

    @field_validator(
        "geometry",
        "quality_metrics",
        mode="before",
    )
    @classmethod
    def parse_mapping(cls, value: Any) -> dict[str, Any]:
        import json

        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        parsed = json.loads(str(value))
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return parsed

    @field_validator(
        "defects",
        "measurement_methods",
        "mechanism_claims",
        "usable_for",
        "not_usable_for",
        mode="before",
    )
    @classmethod
    def parse_list(cls, value: Any) -> list[Any]:
        import json

        if isinstance(value, list):
            return value
        if value in (None, ""):
            return []
        parsed = json.loads(str(value))
        if not isinstance(parsed, list):
            raise ValueError("expected JSON array")
        return parsed


class PageText(BaseModel):
    page_number: int
    text: str


class ParsedPdf(BaseModel):
    artifact: dict[str, Any]
    metadata: dict[str, Any]
    pages: list[PageText] = Field(default_factory=list)
    page_count: int = 0
    average_chars_per_page: float = 0.0
    parse_status: str = "parsed"
    error_message: str = ""


class LiteratureSectionData(BaseModel):
    section_id: str
    paper_id: str
    artifact_id: str | None = None
    section_type: str = "unknown"
    section_title: str = ""
    page_start: int
    page_end: int
    text: str
    text_hash: str
    parser_version: str


class LiteratureChunkData(BaseModel):
    chunk_id: str
    paper_id: str
    section_id: str | None = None
    artifact_id: str | None = None
    chunk_index: int
    page_start: int
    page_end: int
    section_type: str = "unknown"
    section_title: str = ""
    content: str
    content_hash: str
    token_estimate: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_level: str = "literature_evidence_candidate"
    review_status: str = "pending_review"
    active: bool = True
