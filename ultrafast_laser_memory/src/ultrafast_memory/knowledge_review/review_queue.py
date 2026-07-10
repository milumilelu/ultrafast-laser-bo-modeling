from __future__ import annotations

import json

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def create_review_task(candidate_id: str, risk_level: str, suggested_action: str) -> dict:
    init_database()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM knowledge_review_task WHERE candidate_id = ? AND review_status = 'pending_review'",
            (candidate_id,),
        ).fetchone()
        if existing:
            return dict(existing)
        now = utc_now_iso()
        record = {
            "review_id": stable_id("rev", candidate_id, now),
            "candidate_id": candidate_id,
            "review_status": "pending_review",
            "priority": _priority_for_risk(risk_level),
            "risk_level": risk_level,
            "assigned_to": None,
            "created_at": now,
            "updated_at": now,
            "due_at": None,
            "auto_suggestion": suggested_action,
            "review_comment": None,
        }
        conn.execute(
            """
            INSERT INTO knowledge_review_task VALUES (
              :review_id, :candidate_id, :review_status, :priority, :risk_level,
              :assigned_to, :created_at, :updated_at, :due_at, :auto_suggestion,
              :review_comment
            )
            """,
            record,
        )
        conn.commit()
    return record


def list_review_tasks(status: str = "pending_review") -> list[dict]:
    init_database()
    with get_connection() as conn:
        if status == "all":
            rows = conn.execute("SELECT * FROM knowledge_review_task ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_review_task WHERE review_status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
    return [dict(row) for row in rows]


def get_review_task(review_id: str) -> dict:
    init_database()
    with get_connection() as conn:
        task = conn.execute("SELECT * FROM knowledge_review_task WHERE review_id = ?", (review_id,)).fetchone()
        if not task:
            raise ValueError(f"review task not found: {review_id}")
        candidate = conn.execute(
            "SELECT * FROM knowledge_candidate WHERE candidate_id = ?",
            (task["candidate_id"],),
        ).fetchone()
        source = None
        if candidate and candidate["source_id"]:
            source = conn.execute(
                "SELECT * FROM external_source_artifact WHERE source_id = ?",
                (candidate["source_id"],),
            ).fetchone()
        conflicts = conn.execute(
            "SELECT * FROM knowledge_conflict WHERE candidate_id = ? ORDER BY created_at DESC",
            (task["candidate_id"],),
        ).fetchall()
        history = conn.execute(
            "SELECT * FROM knowledge_review_action WHERE review_id = ? ORDER BY created_at",
            (review_id,),
        ).fetchall()
    candidate_dict = _candidate_dict(dict(candidate)) if candidate else None
    return {
        **dict(task),
        "candidate": candidate_dict,
        "source": dict(source) if source else None,
        "auto_precheck": {
            "risk_level": task["risk_level"],
            "suggested_action": task["auto_suggestion"],
        },
        "conflicts": [dict(row) for row in conflicts],
        "history": [dict(row) for row in history],
    }


def list_knowledge_candidates(status: str = "pending_review") -> list[dict]:
    init_database()
    with get_connection() as conn:
        if status == "all":
            rows = conn.execute("SELECT * FROM knowledge_candidate ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_candidate WHERE review_status = ? OR status = ? ORDER BY created_at DESC",
                (status, status),
            ).fetchall()
    return [_candidate_dict(dict(row)) for row in rows]


def _candidate_dict(row: dict) -> dict:
    row["parameter"] = _loads(row.get("parameter_json"), {})
    row["condition"] = _loads(row.get("condition_json"), {})
    row["usable_for"] = _loads(row.get("usable_for_json"), [])
    row["not_usable_for"] = _loads(row.get("not_usable_for_json"), [])
    return row


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _priority_for_risk(risk_level: str) -> str:
    return {"critical": "urgent", "high": "high", "medium": "normal", "low": "low"}.get(risk_level, "normal")
