from __future__ import annotations

import json

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def detect_conflicts(candidate: dict) -> list[dict]:
    init_database()
    conflicts: list[dict] = []
    claim = candidate.get("claim") or ""
    with get_connection() as conn:
        duplicate = conn.execute(
            "SELECT candidate_id FROM knowledge_candidate WHERE claim = ? AND candidate_id != ? LIMIT 1",
            (claim, candidate.get("candidate_id")),
        ).fetchone()
    if duplicate:
        conflicts.append(
            _write_conflict(
                candidate["candidate_id"],
                duplicate["candidate_id"],
                "duplicate",
                "相同 claim 已存在于候选知识库。",
            )
        )
    not_usable_for = candidate.get("not_usable_for") or _loads(candidate.get("not_usable_for_json"), [])
    if "BO_training" in not_usable_for:
        conflicts.append(
            {
                "candidate_id": candidate["candidate_id"],
                "conflict_type": "target_policy_conflict",
                "conflict_summary": "候选知识显式标记不可用于 BO_training。",
            }
        )
    return conflicts


def _write_conflict(candidate_id: str, existing_id: str | None, conflict_type: str, summary: str) -> dict:
    now = utc_now_iso()
    record = {
        "conflict_id": stable_id("conflict", candidate_id, existing_id, conflict_type),
        "candidate_id": candidate_id,
        "existing_knowledge_id": existing_id,
        "conflict_type": conflict_type,
        "conflict_summary": summary,
        "status": "open",
        "created_at": now,
        "resolved_at": None,
        "resolution_comment": None,
    }
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM knowledge_conflict WHERE conflict_id = ?", (record["conflict_id"],)).fetchone()
        if existing:
            return dict(existing)
        conn.execute(
            """
            INSERT INTO knowledge_conflict VALUES (
              :conflict_id, :candidate_id, :existing_knowledge_id, :conflict_type,
              :conflict_summary, :status, :created_at, :resolved_at, :resolution_comment
            )
            """,
            record,
        )
        conn.execute("UPDATE knowledge_candidate SET conflict_flag = 1 WHERE candidate_id = ?", (candidate_id,))
        conn.commit()
    return record


def _loads(value, default):
    if not value:
        return default
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
