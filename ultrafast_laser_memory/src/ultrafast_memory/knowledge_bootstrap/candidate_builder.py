from __future__ import annotations

import json

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_bootstrap.auto_precheck import run_auto_precheck


def build_knowledge_candidate(source_record: dict, extracted_claim: dict) -> dict:
    init_database()
    candidate_id = stable_id("kc", source_record.get("source_id"), extracted_claim.get("claim"))
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM knowledge_candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if existing:
            return _row_to_candidate(dict(existing))

    candidate = {
        "candidate_id": candidate_id,
        "source_id": source_record.get("source_id"),
        "claim": extracted_claim.get("claim") or "",
        "material": extracted_claim.get("material"),
        "process_type": extracted_claim.get("process_type"),
        "component_type": extracted_claim.get("component_type"),
        "parameter": extracted_claim.get("parameter") or {},
        "condition": extracted_claim.get("condition") or {},
        "usable_for": extracted_claim.get("usable_for") or [],
        "not_usable_for": extracted_claim.get("not_usable_for") or [],
        "evidence_type": extracted_claim.get("evidence_type") or "web_evidence",
        "confidence": float(extracted_claim.get("confidence") or 0.0),
        "status": extracted_claim.get("status") or "candidate",
        "review_status": "pending_review",
        "source_quality_score": source_record.get("credibility_score") or 0.5,
        "created_at": utc_now_iso(),
        "reviewed_by": None,
        "review_comment": None,
    }
    precheck = run_auto_precheck(candidate)
    candidate["risk_level"] = precheck["risk_level"]
    candidate["suggested_action"] = precheck["suggested_action"]
    candidate["conflict_flag"] = precheck["conflict_flag"]
    candidate["duplicate_of"] = precheck["duplicate_of"]

    record = {
        **candidate,
        "parameter_json": json.dumps(candidate["parameter"], ensure_ascii=False),
        "condition_json": json.dumps(candidate["condition"], ensure_ascii=False),
        "usable_for_json": json.dumps(candidate["usable_for"], ensure_ascii=False),
        "not_usable_for_json": json.dumps(candidate["not_usable_for"], ensure_ascii=False),
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_candidate (
              candidate_id, source_id, claim, material, process_type, component_type,
              parameter_json, condition_json, usable_for_json, not_usable_for_json,
              evidence_type, confidence, status, review_status, risk_level,
              suggested_action, conflict_flag, duplicate_of, source_quality_score,
              created_at, reviewed_by, review_comment
            ) VALUES (
              :candidate_id, :source_id, :claim, :material, :process_type, :component_type,
              :parameter_json, :condition_json, :usable_for_json, :not_usable_for_json,
              :evidence_type, :confidence, :status, :review_status, :risk_level,
              :suggested_action, :conflict_flag, :duplicate_of, :source_quality_score,
              :created_at, :reviewed_by, :review_comment
            )
            """,
            record,
        )
        conn.commit()
    return candidate


def _row_to_candidate(row: dict) -> dict:
    return {
        **row,
        "parameter": _loads(row.get("parameter_json"), {}),
        "condition": _loads(row.get("condition_json"), {}),
        "usable_for": _loads(row.get("usable_for_json"), []),
        "not_usable_for": _loads(row.get("not_usable_for_json"), []),
    }


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
