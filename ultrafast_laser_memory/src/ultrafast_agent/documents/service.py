from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any
import uuid

from ultrafast_agent.jobs import BackgroundJobService
from ultrafast_domain.documents import OcrDocument
from ultrafast_integrations.ocr import OcrProvider
from ultrafast_integrations.storage.ocr_repository import OcrDocumentRepository


class DocumentIngestionService:
    def __init__(self, jobs: BackgroundJobService):
        self.jobs = jobs

    def ingest(self, artifact: dict[str, Any], *, parser_version: str = "3.x-adapter-1.0") -> dict[str, Any]:
        path = Path(artifact["path"]).resolve()
        source_hash = artifact.get("sha256") or _hash(path)
        if path.suffix.lower() == ".pdf" and _native_pdf_has_text(path):
            return {"status": "native_text", "ocr_job_created": False, "source_hash": source_hash}
        job, created = self.jobs.create(
            "paddleocr_document",
            {**artifact, "path": str(path), "sha256": source_hash, "parser_version": parser_version},
            idempotency_key=f"{source_hash}:{parser_version}", timeout_seconds=3600,
        )
        return {"status": "queued", "ocr_job_created": created, "job_id": job.job_id, "source_hash": source_hash}


def build_paddleocr_job_handler(provider: OcrProvider, repository: OcrDocumentRepository | None = None):
    storage = repository or OcrDocumentRepository()

    def handler(payload: dict[str, Any], context: Any) -> dict[str, Any]:
        context.progress(0.05, "loading_document")
        document = provider.parse(payload)
        context.progress(0.9, "persisting_elements", {"elements": len(document.elements)})
        storage.save(document)
        return {
            "document_id": document.document_id, "element_count": len(document.elements),
            "failed_pages": list(document.failed_pages),
        }

    return handler


class OcrQualityGate:
    def extract_numeric_candidates(self, document: OcrDocument) -> list[dict[str, Any]]:
        candidates = []
        pattern = re.compile(r"(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>nm|µm|um|fs|ps|W|kHz|MHz|mm/s|uJ)", re.I)
        for element in document.elements:
            for match in pattern.finditer(element.content):
                confidence = element.confidence
                candidates.append(
                    {
                        "candidate_id": f"document_parameter_candidate_{uuid.uuid4().hex}",
                        "document_id": document.document_id, "element_id": element.element_id,
                        "raw_value": match.group(0), "value": float(match.group("value")),
                        "unit": match.group("unit"), "confidence": confidence,
                        "validation_status": "candidate_only",
                        "review_status": "pending_review" if confidence is None or confidence < 0.95 else "requires_parameter_identification",
                        "allowed_destinations": [],
                    }
                )
        return candidates


def _native_pdf_has_text(path: Path) -> bool:
    try:
        import fitz  # type: ignore

        document = fitz.open(str(path))
        try:
            if not len(document):
                return False
            average = sum(len(re.sub(r"\s+", "", page.get_text("text") or "")) for page in document) / len(document)
            return average >= 50
        finally:
            document.close()
    except Exception:
        return False


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
