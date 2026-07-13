from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
from pathlib import Path
from typing import Any, Callable
import uuid

from ultrafast_domain.documents import DocumentElement, OcrDocument


class OcrProvider(ABC):
    @abstractmethod
    def parse(self, artifact: dict[str, Any]) -> OcrDocument: ...


class PaddleOcrProvider(OcrProvider):
    parser_name = "paddleocr"

    def __init__(self, engine: Any | None = None, *, parser_version: str = "3.x-adapter-1.0", engine_factory: Callable[[], Any] | None = None):
        self._engine = engine
        self._engine_factory = engine_factory
        self.parser_version = parser_version

    def parse(self, artifact: dict[str, Any]) -> OcrDocument:
        path = Path(artifact["path"]).resolve()
        source_hash = artifact.get("sha256") or _sha256(path)
        document_id = f"ocr_document_{source_hash[:20]}_{hashlib.sha256(self.parser_version.encode()).hexdigest()[:8]}"
        engine = self._get_engine()
        try:
            raw = engine.ocr(str(path), cls=True)
        except TypeError:
            raw = engine.predict(str(path))
        elements: list[DocumentElement] = []
        for page_index, page in enumerate(raw or [], start=1):
            for line_index, item in enumerate(_lines(page), start=1):
                bbox, text, confidence = item
                elements.append(
                    DocumentElement(
                        document_id=document_id, page_number=page_index,
                        element_id=f"document_element_{uuid.uuid4().hex}", element_type="paragraph",
                        content=str(text), bbox=_bbox(bbox), confidence=float(confidence) if confidence is not None else None,
                        parser_name=self.parser_name, parser_version=self.parser_version,
                        source_image_hash=source_hash, review_status="unreviewed",
                    )
                )
        return OcrDocument(
            document_id=document_id, artifact_id=str(artifact.get("artifact_id") or source_hash),
            parser_name=self.parser_name, parser_version=self.parser_version, source_hash=source_hash,
            elements=tuple(elements), review_status="unreviewed",
        )

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self._engine_factory:
            self._engine = self._engine_factory()
            return self._engine
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            error = RuntimeError("PaddleOCR provider is unavailable; install the optional 'ocr' dependencies")
            error.code = "provider_unavailable"  # type: ignore[attr-defined]
            raise error from exc
        self._engine = PaddleOCR(use_angle_cls=True, lang="ch")
        return self._engine


def _lines(page: Any) -> list[tuple[Any, str, float | None]]:
    result = []
    if isinstance(page, dict):
        texts = page.get("rec_texts") or []
        scores = page.get("rec_scores") or [None] * len(texts)
        boxes = page.get("rec_boxes") or page.get("dt_polys") or [None] * len(texts)
        return list(zip(boxes, texts, scores))
    for item in page or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            recognition = item[1]
            if isinstance(recognition, (list, tuple)) and recognition:
                result.append((item[0], str(recognition[0]), recognition[1] if len(recognition) > 1 else None))
    return result


def _bbox(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    points = list(value)
    if len(points) == 4 and all(isinstance(item, (int, float)) for item in points):
        return tuple(map(float, points))  # type: ignore[return-value]
    flat = [coordinate for point in points for coordinate in point]
    xs, ys = flat[0::2], flat[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

