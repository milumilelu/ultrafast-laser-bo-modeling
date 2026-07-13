from __future__ import annotations

from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


FORBIDDEN_TRACE_KEYS = {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens"}
VALID_EVENT_TYPES = {
    "workflow_start",
    "workflow_progress",
    "state_update",
    "thinking_summary",
    "tool_call",
    "tool_result",
    "knowledge_lookup",
    "device_lookup",
    "equipment_profile_loaded",
    "question_generated",
    "decision",
    "warning",
    "error",
    "workflow_end",
}


def record_agent_trace_event(
    session_id: str,
    event_type: str,
    title: str,
    summary: str,
    message_id: str | None = None,
    stage: str | None = None,
    progress: int | float | None = None,
    skill: str | None = None,
    tool: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    init_database()
    if event_type not in VALID_EVENT_TYPES:
        event_type = "state_update"
    safe = _strip_forbidden(
        {
            "session_id": session_id,
            "message_id": message_id,
            "event_type": event_type,
            "stage": stage,
            "title": title,
            "summary": summary,
            "progress": int(progress) if progress is not None else None,
            "skill": skill,
            "tool": tool,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "status": status,
            "created_at": utc_now_iso(),
        }
    )
    safe["event_id"] = stable_id("agenttrace", session_id, message_id or "", event_type, title, safe["created_at"])
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_trace_event VALUES (
              :event_id, :session_id, :message_id, :event_type, :stage, :title,
              :summary, :progress, :skill, :tool, :input_summary,
              :output_summary, :status, :created_at
            )
            """,
            safe,
        )
        conn.commit()
    return safe


def list_agent_trace_events(session_id: str, message_id: str | None = None) -> list[dict[str, Any]]:
    init_database()
    params: list[Any] = [session_id]
    where = "session_id = ?"
    if message_id is not None:
        where += " AND message_id = ?"
        params.append(message_id)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT event_id, session_id, message_id, event_type, stage, title, summary,
                   progress, skill, tool, input_summary, output_summary, status, created_at
            FROM agent_trace_event
            WHERE {where}
            ORDER BY created_at, event_id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def trace_from_progress(session_id: str, message_id: str | None, progress: dict[str, Any], skill: str | None = None) -> dict[str, Any]:
    return record_agent_trace_event(
        session_id=session_id,
        message_id=message_id,
        event_type="workflow_progress",
        stage=progress.get("current_stage"),
        title="任务进度",
        summary=progress.get("message") or "",
        progress=progress.get("progress_percent"),
        skill=skill or progress.get("workflow_type"),
        status=progress.get("status"),
    )


def trace_from_public_status(session_id: str, message_id: str | None, status_event: dict[str, Any], skill: str | None = None) -> dict[str, Any]:
    event_type = status_event.get("event_type") or "thinking_summary"
    mapped = {
        "equipment_profile_loaded": "device_lookup",
        "evidence_gap_check": "knowledge_lookup",
        "slot_check": "state_update",
        "task_parsed": "state_update",
    }.get(event_type, "thinking_summary")
    return record_agent_trace_event(
        session_id=session_id,
        message_id=message_id,
        event_type=mapped,
        stage=event_type,
        title=status_event.get("title") or "公开推理摘要",
        summary=status_event.get("summary") or "",
        skill=skill,
        tool="equipment_memory" if event_type == "equipment_profile_loaded" else None,
        status="completed",
    )


def _strip_forbidden(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in FORBIDDEN_TRACE_KEYS}
