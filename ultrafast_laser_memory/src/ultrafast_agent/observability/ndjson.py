from __future__ import annotations

from typing import Any

from ultrafast_agent.runtime.events import redact_public_data


NORMAL_VISIBLE = {
    "meta",
    "progress",
    "workflow_state",
    "delta",
    "done",
    "warning",
    "error",
    "workflow_start",
    "workflow_end",
    "workflow_started",
    "workflow_completed",
    "workflow_failed",
    "decision",
    "question_generated",
}


def normalize_stream_event(event: dict[str, Any], sequence: int, mode: str = "normal") -> dict[str, Any] | None:
    value = redact_public_data(dict(event))
    event_type = str(value.get("event_type") or value.get("type") or "state_update")
    value.setdefault("type", event.get("type") or "agent_trace")
    value["event_type"] = event_type
    value["sequence"] = sequence
    value.setdefault("stage", event.get("step") or "chat")
    value.setdefault("status", "running" if event_type not in {"done", "error"} else "completed")
    value.setdefault("title", _title(event_type))
    value.setdefault("summary", _summary(value))
    display_mode = (mode or "normal").lower()
    if display_mode == "normal":
        if event_type not in NORMAL_VISIBLE and value.get("type") not in NORMAL_VISIBLE:
            value["collapsed"] = True
        value.pop("input_summary", None)
        value.pop("output_summary", None)
        value.pop("data", None)
    elif display_mode == "research":
        if isinstance(value.get("data"), dict):
            value["data"] = {
                key: item
                for key, item in value["data"].items()
                if key in {"evidence_count", "citation_count", "route", "skill", "tool", "model_status"}
            }
    return value


def _title(event_type: str) -> str:
    return {
        "meta": "会话元数据",
        "progress": "工作流进度",
        "delta": "模型响应",
        "done": "响应完成",
        "tool_call": "调用工具",
        "tool_result": "工具完成",
        "decision": "决策",
        "warning": "警告",
        "error": "错误",
    }.get(event_type, "执行状态")


def _summary(event: dict[str, Any]) -> str:
    if event.get("message"):
        return str(event["message"])
    if event.get("content") and event.get("type") != "delta":
        return str(event["content"])[:200]
    if event.get("step"):
        return str(event["step"])
    return ""
