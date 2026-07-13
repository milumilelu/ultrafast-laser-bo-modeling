from __future__ import annotations

from datetime import datetime, timezone
import json

from ultrafast_domain.documents import OcrDocument
from ultrafast_memory.db.session import get_connection


class OcrDocumentRepository:
    def save(self, document: OcrDocument) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ocr_document VALUES (?,?,?,?,?,?,?)",
                (document.document_id, document.artifact_id, document.parser_name, document.parser_version, document.source_hash, document.review_status, now),
            )
            for element in document.elements:
                conn.execute(
                    "INSERT OR IGNORE INTO document_element VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (element.element_id, element.document_id, element.page_number, element.element_type, element.content,
                     json.dumps(element.bbox), element.confidence, element.parser_name, element.parser_version,
                     element.source_image_hash, element.review_status, now),
                )
            conn.commit()
