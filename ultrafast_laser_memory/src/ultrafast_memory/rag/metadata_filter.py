from __future__ import annotations

import json
from typing import Any


FILTER_FIELDS = {
    "scenario_id", "material", "material_grade", "process_type", "component_type",
    "laser_type", "evidence_level", "review_status", "section_type",
}

REVIEWED_STATUSES = {
    "accepted", "approved", "reviewed", "accepted_to_rag",
    "accepted_as_literature_evidence",
}
TARGET_LEVEL_RANK = {
    "LEVEL_0_UNVERIFIED_CANDIDATE": 0,
    "LEVEL_1_RAG_BACKGROUND": 1,
    "LEVEL_2_LITERATURE_EVIDENCE": 2,
    "LEVEL_3_PROCESS_PRIOR": 3,
    "LEVEL_4_VALIDATED_RULE": 4,
    "LEVEL_5_BO_TRAINING_SAMPLE": 5,
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
    normalized_purpose = purpose.strip().lower()
    not_usable = metadata.get("not_usable_for") or []
    if isinstance(not_usable, str):
        try:
            not_usable = json.loads(not_usable)
        except json.JSONDecodeError:
            not_usable = [not_usable]
    normalized_not_usable = {str(item).strip().lower() for item in not_usable}
    if normalized_purpose in normalized_not_usable:
        return False
    status = str(hit.get("review_status") or metadata.get("review_status") or "pending_review")
    evidence_level = str(hit.get("evidence_level") or metadata.get("evidence_level") or "")
    target_rank = TARGET_LEVEL_RANK.get(str(metadata.get("target_level") or ""), 0)
    reviewed = status in REVIEWED_STATUSES
    if normalized_purpose in {
        "parameter_recommendation", "rag_parameter_recommendation",
    }:
        return reviewed and (
            target_rank >= 2
            or evidence_level in {"literature_evidence", "process_prior", "validated_rule"}
        )
    if normalized_purpose in {
        "formal_process", "direct_parameter_recommendation", "bo", "bo_boundary",
    }:
        return reviewed and (
            target_rank >= 3 or evidence_level in {"process_prior", "validated_rule"}
        )
    return True


def evidence_authority(hit: dict[str, Any]) -> str:
    metadata = metadata_for_hit(hit)
    status = str(hit.get("review_status") or metadata.get("review_status") or "pending_review")
    evidence_level = str(hit.get("evidence_level") or metadata.get("evidence_level") or "")
    target_rank = TARGET_LEVEL_RANK.get(str(metadata.get("target_level") or ""), 0)
    if status not in REVIEWED_STATUSES:
        return "candidate"
    if target_rank >= 4 or evidence_level == "validated_rule":
        return "validated_rule"
    if target_rank >= 3 or evidence_level == "process_prior":
        return "process_prior"
    if target_rank >= 2 or evidence_level == "literature_evidence":
        return "reviewed_literature"
    return "reviewed_background"
