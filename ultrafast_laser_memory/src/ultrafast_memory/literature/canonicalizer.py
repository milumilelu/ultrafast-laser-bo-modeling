from __future__ import annotations

import re
import unicodedata
from typing import Any


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)


def normalize_doi(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    match = DOI_RE.search(text)
    return match.group(0).rstrip(".,;)") if match else ""


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text).strip()


def merge_metadata(structured: dict[str, Any], extracted: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    merged = dict(extracted)
    conflicts: list[dict[str, Any]] = []
    for key, structured_value in structured.items():
        if structured_value in (None, "", [], {}):
            continue
        extracted_value = extracted.get(key)
        if extracted_value not in (None, "", [], {}) and _comparable(structured_value) != _comparable(extracted_value):
            conflicts.append(
                {
                    "field": key,
                    "structured_value": structured_value,
                    "extracted_value": extracted_value,
                    "canonical_value": structured_value,
                }
            )
        merged[key] = structured_value
    if conflicts:
        merged["review_status"] = "needs_review"
        merged["conflicts"] = conflicts
    return merged, conflicts


def _comparable(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().lower()
    return repr(value)
