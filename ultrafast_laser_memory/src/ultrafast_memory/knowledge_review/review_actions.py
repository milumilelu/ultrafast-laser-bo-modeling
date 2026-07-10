from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_review.review_policy import IMPLEMENTED_ACTIONS, STUB_ACTIONS
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest
from ultrafast_memory.rag.document_builder import build_rag_document_from_candidate
from ultrafast_memory.rag.index_stub import index_rag_document


def apply_review_action(review_id: str, request: ReviewActionRequest) -> dict:
    init_database()
    if request.action in STUB_ACTIONS:
        return {
            "status": "not_implemented_in_mvp",
            "message": f"{request.action} requires structured validation beyond MVP.",
        }
    if request.action not in IMPLEMENTED_ACTIONS:
        raise ValueError(f"unsupported review action: {request.action}")

    with get_connection() as conn:
        task = conn.execute("SELECT * FROM knowledge_review_task WHERE review_id = ?", (review_id,)).fetchone()
        if not task:
            raise ValueError(f"review task not found: {review_id}")
        candidate = conn.execute(
            "SELECT * FROM knowledge_candidate WHERE candidate_id = ?",
            (task["candidate_id"],),
        ).fetchone()
        if not candidate:
            raise ValueError(f"knowledge candidate not found: {task['candidate_id']}")
        source = conn.execute(
            "SELECT * FROM external_source_artifact WHERE source_id = ?",
            (candidate["source_id"],),
        ).fetchone()

    candidate_dict = _candidate_dict(dict(candidate))
    source_dict = dict(source) if source else {}
    now = utc_now_iso()
    rag_doc = None
    literature_evidence = None

    if request.action == "reject":
        review_status = "rejected"
        candidate_status = "rejected"
    elif request.action == "needs_more_evidence":
        review_status = "needs_more_evidence"
        candidate_status = "needs_more_evidence"
    elif request.action == "withdraw":
        review_status = "withdrawn"
        candidate_status = "withdrawn"
    elif request.action == "accept_to_rag":
        review_status = "accepted_to_rag"
        candidate_status = "accepted"
        candidate_dict["review_status"] = review_status
        rag_doc = build_rag_document_from_candidate(candidate_dict, source_dict)
        index_rag_document(rag_doc["rag_doc_id"], request.payload.get("index_name", "default"))
    elif request.action == "accept_as_literature_evidence":
        review_status = "accepted_as_literature_evidence"
        candidate_status = "accepted"
        literature_evidence = _write_literature_evidence(candidate_dict, now)
        candidate_dict["review_status"] = review_status
        rag_doc = build_rag_document_from_candidate(candidate_dict, source_dict)
        index_rag_document(rag_doc["rag_doc_id"], request.payload.get("index_name", "default"))

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE knowledge_candidate
            SET status = ?, review_status = ?, reviewed_by = ?, review_comment = ?
            WHERE candidate_id = ?
            """,
            (candidate_status, review_status, request.reviewer_id, request.comment, candidate_dict["candidate_id"]),
        )
        conn.execute(
            """
            UPDATE knowledge_review_task
            SET review_status = ?, updated_at = ?, review_comment = ?
            WHERE review_id = ?
            """,
            (review_status, now, request.comment, review_id),
        )
        action = {
            "action_id": stable_id("kra", review_id, request.action, request.reviewer_id, now),
            "review_id": review_id,
            "candidate_id": candidate_dict["candidate_id"],
            "reviewer_id": request.reviewer_id,
            "action": request.action,
            "target_level": request.target_level,
            "comment": request.comment,
            "created_at": now,
            "payload_json": json.dumps(request.payload, ensure_ascii=False),
        }
        conn.execute(
            """
            INSERT INTO knowledge_review_action VALUES (
              :action_id, :review_id, :candidate_id, :reviewer_id, :action,
              :target_level, :comment, :created_at, :payload_json
            )
            """,
            action,
        )
        conn.commit()

    _update_linked_chat_sessions(candidate_dict["candidate_id"], review_id, review_status, rag_doc)
    return {
        "status": review_status,
        "review_id": review_id,
        "candidate_id": candidate_dict["candidate_id"],
        "rag_document": rag_doc,
        "literature_evidence": literature_evidence,
    }


def _write_literature_evidence(candidate: dict, now: str) -> dict:
    record = {
        "evidence_id": stable_id("lit", candidate["candidate_id"], candidate.get("claim")),
        "source_id": candidate.get("source_id"),
        "candidate_id": candidate.get("candidate_id"),
        "claim": candidate.get("claim"),
        "material": candidate.get("material"),
        "process_type": candidate.get("process_type"),
        "component_type": candidate.get("component_type"),
        "metric_name": None,
        "parameter_range_json": json.dumps(candidate.get("parameter") or {}, ensure_ascii=False),
        "condition_json": json.dumps(candidate.get("condition") or {}, ensure_ascii=False),
        "page_or_section": None,
        "confidence": candidate.get("confidence"),
        "created_at": now,
    }
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM literature_evidence WHERE evidence_id = ?", (record["evidence_id"],)).fetchone()
        if existing:
            return dict(existing)
        conn.execute(
            """
            INSERT INTO literature_evidence VALUES (
              :evidence_id, :source_id, :candidate_id, :claim, :material, :process_type,
              :component_type, :metric_name, :parameter_range_json, :condition_json,
              :page_or_section, :confidence, :created_at
            )
            """,
            record,
        )
        conn.commit()
    return record


def _update_linked_chat_sessions(candidate_id: str, review_id: str, review_status: str, rag_doc: dict | None) -> None:
    with get_connection() as conn:
        rows = conn.execute("SELECT session_id, active_knowledge_bootstrap_json FROM chat_session_state").fetchall()
    for row in rows:
        active = _loads(row["active_knowledge_bootstrap_json"], {})
        if candidate_id not in (active.get("candidate_ids") or []):
            continue
        accepted = set(active.get("accepted_candidate_ids") or [])
        accepted_rag = set(active.get("accepted_rag_doc_ids") or [])
        completed = set(active.get("completed_review_task_ids") or [])
        if review_status in {"accepted_to_rag", "accepted_as_literature_evidence"}:
            accepted.add(candidate_id)
            if rag_doc:
                accepted_rag.add(rag_doc["rag_doc_id"])
        if review_status in {"accepted_to_rag", "accepted_as_literature_evidence", "rejected", "needs_more_evidence", "withdrawn"}:
            completed.add(review_id)
        all_tasks = set(active.get("review_task_ids") or [])
        active["accepted_candidate_ids"] = sorted(accepted)
        active["accepted_rag_doc_ids"] = sorted(accepted_rag)
        active["completed_review_task_ids"] = sorted(completed)
        active["status"] = "reviewed" if all_tasks and all_tasks.issubset(completed) else "partially_reviewed"
        state = get_session_state(row["session_id"])
        pending = [task_id for task_id in state.get("pending_review_task_ids", []) if task_id != review_id]
        update_session_state(
            row["session_id"],
            {"active_knowledge_bootstrap": active, "pending_review_task_ids": pending},
        )


def _candidate_dict(row: dict) -> dict[str, Any]:
    row["parameter"] = _loads(row.get("parameter_json"), {})
    row["condition"] = _loads(row.get("condition_json"), {})
    row["usable_for"] = _loads(row.get("usable_for_json"), [])
    row["not_usable_for"] = _loads(row.get("not_usable_for_json"), [])
    return row


def _loads(value, default):
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
