from __future__ import annotations

from typing import Any

from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.agent_runtime.trace_collector import list_agent_trace_events
from ultrafast_memory.process_workflow.repository import ProcessWorkflowRepository


REASONING_EVENT_TYPES = {
    "thinking_summary",
    "decision",
    "knowledge_lookup",
    "warning",
    "error",
}


def reasoning_view(session_id: str) -> dict[str, Any]:
    events = [
        event
        for event in list_agent_trace_events(session_id)
        if event.get("event_type") in REASONING_EVENT_TYPES
    ]
    return {
        "session_id": session_id,
        "trace_type": "公开推理摘要",
        "events": events,
        "note": "仅含可审计的公开摘要，不含模型隐藏思维链。",
    }


def waterfall_view(session_id: str) -> dict[str, Any]:
    events = RuntimeEventRepository().list_session_events(session_id)
    timed = [
        {
            "sequence": event.get("sequence"),
            "stage": event.get("stage"),
            "title": event.get("title"),
            "tool": event.get("tool_name"),
            "duration_ms": event.get("duration_ms"),
            "status": event.get("status"),
        }
        for event in events
        if event.get("duration_ms") is not None
    ]
    return {
        "session_id": session_id,
        "total_duration_ms": round(sum(float(item["duration_ms"]) for item in timed), 3),
        "events": timed,
    }


def campaign_view(session_id: str) -> dict[str, Any]:
    campaigns = ProcessWorkflowRepository().list_campaigns_for_task(f"process-{session_id}")
    return {"session_id": session_id, "campaigns": campaigns}


def model_view(session_id: str) -> dict[str, Any]:
    snapshots = ProcessWorkflowRepository().list_model_snapshots_for_task(f"process-{session_id}")
    return {"session_id": session_id, "model_snapshots": snapshots}
