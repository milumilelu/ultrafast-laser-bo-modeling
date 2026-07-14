from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_agent.observability import DebugTraceRenderer, NDJSONRenderer, TUIRenderer
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


FORBIDDEN = {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens"}


def test_legacy_trace_adapter_writes_only_canonical_event_store(isolated_root):
    init_database()

    event = record_agent_trace_event(
        "trace-session",
        "device_lookup",
        "读取设备配置",
        "已加载设备边界。",
        output_summary="ok",
    )

    assert not (FORBIDDEN & set(event))
    with get_connection() as conn:
        canonical = conn.execute(
            "SELECT COUNT(*) FROM runtime_public_event WHERE session_id = ?", ("trace-session",)
        ).fetchone()[0]
        legacy = conn.execute(
            "SELECT COUNT(*) FROM agent_trace_event WHERE session_id = ?", ("trace-session",)
        ).fetchone()[0]
    assert canonical == 1
    assert legacy == 0


def test_renderers_share_one_canonical_event_without_extra_write(isolated_root):
    event = record_agent_trace_event(
        "render-session", "field_extraction_completed", "字段抽取结果", "已完成字段抽取。"
    )
    assert {
        "event_id", "sequence", "timestamp", "session_id", "workflow_id",
        "event_type", "stage", "step", "tool", "skill", "status",
        "public_summary", "payload",
    } <= set(event)

    rendered = [
        NDJSONRenderer().render(event, render_sequence=1, mode="debug"),
        TUIRenderer().render(event),
        DebugTraceRenderer().render(event),
    ]
    assert {item["event_id"] for item in rendered} == {event["event_id"]}
    assert {item["sequence"] for item in rendered} == {event["sequence"]}
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM runtime_public_event WHERE session_id = 'render-session'"
        ).fetchone()[0]
    assert count == 1


def test_chat_response_contains_execution_trace_and_agent_trace_api(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="我想加工金刚石CRL，Ra小于460nm", use_skills=False))

    assert response.execution_trace
    assert any(event["event_type"] == "workflow_progress" for event in response.execution_trace)
    assert not any(FORBIDDEN & set(event) for event in response.execution_trace)

    client = TestClient(app)
    api_response = client.get(f"/chat/sessions/{response.session_id}/agent-trace")
    assert api_response.status_code == 200
    assert api_response.json()["events"]


def test_stream_ndjson_emits_agent_trace_event(isolated_root):
    init_database()
    client = TestClient(app)

    response = client.post("/chat/stream_ndjson", json={"message": "我想加工金刚石CRL", "use_skills": False})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]

    assert "agent_trace" in [event["type"] for event in events]
    assert not any("hidden_reasoning" in event for event in events)


def test_stream_ndjson_emits_tool_call_and_tool_result_trace(isolated_root):
    init_database()
    client = TestClient(app)

    response = client.post("/chat/stream_ndjson", json={"message": "hello", "use_skills": False})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    trace_events = [event for event in events if event["type"] == "agent_trace"]

    assert any(event["event_type"] == "tool_call" and event["tool"] == "llm_adapter" for event in trace_events)
    assert any(event["event_type"] == "tool_result" and event["tool"] == "llm_adapter" for event in trace_events)


def test_mode_command_updates_session_display_mode(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="/mode debug"))
    state = get_session_state(response.session_id)

    assert "debug" in response.assistant_message
    assert state["collected_slots"]["display_mode"] == "debug"
