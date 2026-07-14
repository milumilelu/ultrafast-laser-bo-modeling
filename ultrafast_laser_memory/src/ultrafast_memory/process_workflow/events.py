from __future__ import annotations

from typing import Any

from ultrafast_agent.runtime.event_service import canonical_agent_events
from ultrafast_agent.runtime.events import redact_public_data
from ultrafast_memory.core.ids import stable_id


def record_process_event(
    session_id: str,
    event_type: str,
    title: str,
    summary: str,
    message_id: str | None = None,
    stage: str | None = None,
    progress: int | float | None = None,
    skill: str | None = "process_planning",
    tool: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str | None = None,
    workflow_id: str | None = None,
    visibility: str = "public",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Publish one canonical process event without crossing a legacy Trace API."""
    run_id = stable_id("agent-run", session_id, message_id or "session")
    event = canonical_agent_events.emit(
        run_id=run_id,
        session_id=session_id,
        message_id=message_id,
        workflow_id=workflow_id or stable_id("workflow", session_id, skill or "process"),
        event_type=event_type,
        stage=stage or "process",
        step=stage or event_type,
        title=title,
        public_summary=summary,
        status=status or "completed",
        progress=int(progress) if progress is not None else None,
        skill=skill,
        tool=tool,
        payload=redact_public_data({
            **(payload or {}),
            "input_summary": input_summary,
            "output_summary": output_summary,
        }),
        visibility=visibility,
        idempotency_key=idempotency_key,
    )
    return event.to_dict()
