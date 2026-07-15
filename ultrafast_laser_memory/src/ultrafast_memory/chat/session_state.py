from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


STATE_DEFAULTS = {
    "active_workflow": None,
    "active_skill": None,
    "workflow_stage": None,
    "collected_slots": {},
    "pending_questions": [],
    "allowed_next_skills": [],
    "debug_router": False,
    "streaming_enabled": False,
    "evidence_gap": {},
    "active_knowledge_bootstrap": {},
    "pending_review_task_ids": [],
    "pending_bootstrap_permission": False,
    "active_skills_json": [],
    "agent_observations_json": [],
    "agent_decision_count": 0,
    "last_agent_action_json": {},
    "suggested_skill_hint": {},
}

AGENT_RUNTIME_KEYS = {
    "active_skills_json", "agent_observations_json", "agent_decision_count",
    "last_agent_action_json", "suggested_skill_hint",
}


def create_or_get_session_state(session_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM chat_session_state WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            return _row_to_state(dict(row))
        now = utc_now_iso()
        state_id = stable_id("state", session_id)
        conn.execute(
            """
            INSERT INTO chat_session_state (
              state_id, session_id, active_workflow, active_skill, workflow_stage,
              collected_slots_json, pending_questions_json, allowed_next_skills_json,
              debug_router, streaming_enabled, evidence_gap_json,
              active_knowledge_bootstrap_json, pending_review_task_ids_json,
              pending_bootstrap_permission, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state_id,
                session_id,
                None,
                None,
                None,
                "{}",
                "[]",
                "[]",
                0,
                0,
                "{}",
                "{}",
                "[]",
                0,
                now,
            ),
        )
        conn.commit()
    return get_session_state(session_id)


def get_session_state(session_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM chat_session_state WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        return {**STATE_DEFAULTS, "session_id": session_id}
    return _row_to_state(dict(row))


def update_session_state(session_id: str, state_update: dict[str, Any]) -> dict[str, Any]:
    current = create_or_get_session_state(session_id)
    merged = {**current}
    for key in ("active_workflow", "active_skill", "workflow_stage"):
        if key in state_update and state_update[key] is not None:
            merged[key] = state_update[key]
    for key in (
        "collected_slots",
        "pending_questions",
        "allowed_next_skills",
        "evidence_gap",
        "active_knowledge_bootstrap",
        "pending_review_task_ids",
    ):
        if key in state_update and state_update[key] is not None:
            if key == "collected_slots":
                merged[key] = {**(merged.get(key) or {}), **state_update[key]}
            elif key in {"evidence_gap", "active_knowledge_bootstrap"}:
                merged[key] = state_update[key]
            else:
                merged[key] = state_update[key]
    if "debug_router" in state_update:
        merged["debug_router"] = bool(state_update["debug_router"])
    if "streaming_enabled" in state_update:
        merged["streaming_enabled"] = bool(state_update["streaming_enabled"])
    if "pending_bootstrap_permission" in state_update:
        merged["pending_bootstrap_permission"] = bool(state_update["pending_bootstrap_permission"])
    runtime = dict((merged.get("collected_slots") or {}).get("_agent_runtime") or {})
    for key in AGENT_RUNTIME_KEYS:
        if key in state_update:
            merged[key] = state_update[key]
            runtime[key] = state_update[key]
    if runtime:
        merged["collected_slots"] = {**(merged.get("collected_slots") or {}), "_agent_runtime": runtime}
    _persist_state(session_id, merged)
    return get_session_state(session_id)


def reset_session_state(session_id: str) -> None:
    create_or_get_session_state(session_id)
    current = get_session_state(session_id)
    reset = {
        **STATE_DEFAULTS,
        "debug_router": current.get("debug_router", False),
        "streaming_enabled": current.get("streaming_enabled", False),
    }
    _persist_state(session_id, reset)


def set_debug_router(session_id: str, enabled: bool) -> None:
    update_session_state(session_id, {"debug_router": enabled})


def set_streaming_enabled(session_id: str, enabled: bool) -> None:
    update_session_state(session_id, {"streaming_enabled": enabled})


def _persist_state(session_id: str, state: dict[str, Any]) -> None:
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE chat_session_state SET
              active_workflow = ?,
              active_skill = ?,
              workflow_stage = ?,
              collected_slots_json = ?,
              pending_questions_json = ?,
              allowed_next_skills_json = ?,
              debug_router = ?,
              streaming_enabled = ?,
              evidence_gap_json = ?,
              active_knowledge_bootstrap_json = ?,
              pending_review_task_ids_json = ?,
              pending_bootstrap_permission = ?,
              updated_at = ?
            WHERE session_id = ?
            """,
            (
                state.get("active_workflow"),
                state.get("active_skill"),
                state.get("workflow_stage"),
                json.dumps(state.get("collected_slots") or {}, ensure_ascii=False),
                json.dumps(state.get("pending_questions") or [], ensure_ascii=False),
                json.dumps(state.get("allowed_next_skills") or [], ensure_ascii=False),
                int(bool(state.get("debug_router"))),
                int(bool(state.get("streaming_enabled"))),
                json.dumps(state.get("evidence_gap") or {}, ensure_ascii=False),
                json.dumps(state.get("active_knowledge_bootstrap") or {}, ensure_ascii=False),
                json.dumps(state.get("pending_review_task_ids") or [], ensure_ascii=False),
                int(bool(state.get("pending_bootstrap_permission"))),
                now,
                session_id,
            ),
        )
        conn.commit()


def _row_to_state(row: dict[str, Any]) -> dict[str, Any]:
    collected = _loads(row["collected_slots_json"], {})
    runtime = dict(collected.get("_agent_runtime") or {})
    return {
        "state_id": row["state_id"],
        "session_id": row["session_id"],
        "active_workflow": row["active_workflow"],
        "active_skill": row["active_skill"],
        "workflow_stage": row["workflow_stage"],
        "collected_slots": collected,
        "pending_questions": _loads(row["pending_questions_json"], []),
        "allowed_next_skills": _loads(row["allowed_next_skills_json"], []),
        "debug_router": bool(row["debug_router"]),
        "streaming_enabled": bool(row["streaming_enabled"]),
        "evidence_gap": _loads(row.get("evidence_gap_json"), {}),
        "active_knowledge_bootstrap": _loads(row.get("active_knowledge_bootstrap_json"), {}),
        "pending_review_task_ids": _loads(row.get("pending_review_task_ids_json"), []),
        "pending_bootstrap_permission": bool(row.get("pending_bootstrap_permission")),
        "updated_at": row["updated_at"],
        **{key: runtime.get(key, STATE_DEFAULTS[key]) for key in AGENT_RUNTIME_KEYS},
    }


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
