from __future__ import annotations

import json
from typing import Any


FILTER_FIELDS = {
    "scenario_id", "material", "material_grade", "process_type", "component_type",
    "laser_type", "evidence_level", "review_status", "section_type",
}


def metadata_for_hit(hit: dict[str, Any]) -> dict[str, Any]:
    metadata = hit.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    raw = hit.get("metadata_json")
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return {}


def matches_filters(hit: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return hit.get("review_status") != "rejected"
    metadata = metadata_for_hit(hit)
    if (hit.get("review_status") or metadata.get("review_status")) == "rejected":
        return False
    for key, expected in filters.items():
        if expected in (None, "", []):
            continue
        if key == "year_min":
            year = str(metadata.get("year") or hit.get("year") or "")
            if not year.isdigit() or int(year) < int(expected):
                return False
        elif key == "year_max":
            year = str(metadata.get("year") or hit.get("year") or "")
            if not year.isdigit() or int(year) > int(expected):
                return False
        elif key in FILTER_FIELDS:
            actual = metadata.get(key, hit.get(key))
            if key == "material_grade" and not actual:
                actual = metadata.get("material", hit.get("material"))
            allowed = expected if isinstance(expected, list) else [expected]
            if actual not in allowed:
                return False
    return True


def apply_metadata_filters(hits: list[dict[str, Any]], filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [hit for hit in hits if matches_filters(hit, filters)]


def enforce_purpose(hit: dict[str, Any], purpose: str) -> bool:
    metadata = metadata_for_hit(hit)
    not_usable = metadata.get("not_usable_for") or []
    if isinstance(not_usable, str):
        try:
            not_usable = json.loads(not_usable)
        except json.JSONDecodeError:
            not_usable = [not_usable]
    if purpose in not_usable:
        return False
    if purpose in {"BO", "BO_boundary", "direct_parameter_recommendation"}:
        return hit.get("evidence_level") == "process_prior" and hit.get("review_status") in {"accepted", "approved"}
    return True
