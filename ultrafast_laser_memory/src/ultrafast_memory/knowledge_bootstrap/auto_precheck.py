from __future__ import annotations

import json
import re

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


PARAMETER_PATTERN = re.compile(r"(\d+(\.\d+)?\s?(nm|um|µm|fs|ps|w|khz|mm/s|mm s-1|mj|%)\b)", re.IGNORECASE)


def run_auto_precheck(candidate: dict) -> dict:
    init_database()
    issues: list[str] = []
    if not candidate.get("source_id"):
        issues.append("missing_source_id")
    if not candidate.get("claim"):
        issues.append("missing_claim")
    if not candidate.get("material"):
        issues.append("missing_material")
    if not candidate.get("process_type"):
        issues.append("missing_process_type")
    usable_for = candidate.get("usable_for") or _loads(candidate.get("usable_for_json"), [])
    not_usable_for = candidate.get("not_usable_for") or _loads(candidate.get("not_usable_for_json"), [])
    if not usable_for or not not_usable_for:
        issues.append("missing_usage_scope")

    has_parameters = bool(candidate.get("parameter") or _loads(candidate.get("parameter_json"), {}) or PARAMETER_PATTERN.search(candidate.get("claim") or ""))
    duplicate_of = _find_duplicate(candidate)
    if duplicate_of:
        issues.append("duplicate")

    if "missing_claim" in issues:
        risk = "high"
        suggestion = "reject"
    elif has_parameters:
        risk = "high"
        suggestion = "needs_more_evidence"
    elif "missing_source_id" in issues or "missing_material" in issues or "missing_process_type" in issues or "missing_usage_scope" in issues:
        risk = "medium"
        suggestion = "needs_more_evidence"
    else:
        risk = "low"
        suggestion = "accept_to_rag"

    if duplicate_of:
        suggestion = "needs_more_evidence"

    return {
        "risk_level": risk,
        "suggested_action": suggestion,
        "issues": issues,
        "has_parameters": has_parameters,
        "duplicate_of": duplicate_of,
        "conflict_flag": 1 if duplicate_of else 0,
    }


def _find_duplicate(candidate: dict) -> str | None:
    claim = candidate.get("claim")
    if not claim:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT candidate_id FROM knowledge_candidate WHERE claim = ? AND candidate_id != ? LIMIT 1",
            (claim, candidate.get("candidate_id") or ""),
        ).fetchone()
    return row["candidate_id"] if row else None


def _loads(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
