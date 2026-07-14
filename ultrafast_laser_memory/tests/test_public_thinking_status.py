from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.chat.workflow_status import list_public_thinking_status, record_public_trace
from ultrafast_memory.db.init_db import init_database


FORBIDDEN = {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens"}


def test_chat_returns_public_thinking_status_without_forbidden_fields(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="我想加工金刚石CRL，Ra小于460nm", use_skills=True))

    assert response.thinking_status
    for item in response.thinking_status:
        assert not (FORBIDDEN & set(item))


def test_thinking_status_api_returns_only_public_events(isolated_root):
    init_database()
    response = handle_chat(ChatRequest(message="我想加工金刚石CRL", use_skills=True))
    record_public_trace(
        response.session_id,
        "tool_call_started",
        "内部事件",
        "这条 internal 事件不应展示。",
        visibility="internal",
    )

    client = TestClient(app)
    api_response = client.get(f"/chat/sessions/{response.session_id}/thinking-status")

    assert api_response.status_code == 200
    events = api_response.json()["events"]
    assert events
    assert all(event["visibility"] == "public" for event in events)
    assert not any(event["summary"] == "这条 internal 事件不应展示。" for event in events)

    progress_response = client.get(f"/chat/sessions/{response.session_id}/progress")
    assert progress_response.status_code == 200
    progress = progress_response.json()["progress"]
    assert progress is not None
    assert progress["business_state"] == "INTAKE"
    assert progress["progress_percent"] is None


def test_tool_and_evidence_events_can_be_saved_and_queried(isolated_root):
    init_database()

    record_public_trace("session-status", "tool_call_started", "工具调用", "开始检查内部证据。")
    record_public_trace("session-status", "evidence_gap_check", "证据检查", "内部证据不足。")

    events = list_public_thinking_status("session-status")
    assert [event["event_type"] for event in events] == ["tool_call_started", "evidence_gap_check"]
