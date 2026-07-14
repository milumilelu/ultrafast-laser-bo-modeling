from __future__ import annotations

from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_agent.runtime.event_service import canonical_agent_events
from ultrafast_agent.runtime.events import redact_public_data
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.migrations.legacy_trace import legacy_session_fallback


FORBIDDEN_TRACE_KEYS = {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens"}
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
    workflow_id: str | None = None,
    visibility: str = "public",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    run_id = stable_id("agent-run", session_id, message_id or "session")
    workflow_id = workflow_id or stable_id("workflow", session_id, skill or "chat")
    safe_payload = redact_public_data({
        **(payload or {}),
        "input_summary": input_summary,
        "output_summary": output_summary,
    })
    event = canonical_agent_events.emit(
        run_id=run_id,
        session_id=session_id,
        message_id=message_id,
        workflow_id=workflow_id,
        event_type=event_type,
        stage=stage or "chat",
        step=stage or event_type,
        title=title,
        public_summary=summary,
        status=status or "completed",
        progress=int(progress) if progress is not None else None,
        skill=skill,
        tool=tool,
        payload=safe_payload,
        visibility=visibility,
        idempotency_key=idempotency_key,
    )
    return event.to_dict()


def list_agent_trace_events(session_id: str, message_id: str | None = None) -> list[dict[str, Any]]:
    events = RuntimeEventRepository().list_session_events(session_id)
    if message_id is not None:
        events = [event for event in events if event.get("message_id") == message_id]
    if events:
        return events
    return legacy_session_fallback(session_id, message_id)


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
    return redact_public_data(
        {key: value for key, value in record.items() if key not in FORBIDDEN_TRACE_KEYS}
    )
