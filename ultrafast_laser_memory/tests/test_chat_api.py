from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.init_db import init_database


def test_chat_api_end_to_end(isolated_root, monkeypatch):
    secret = "sk-test-secret"
    for key in (
        "ULTRAFAST_LLM_PROVIDER",
        "ULTRAFAST_LLM_MODEL",
        "ULTRAFAST_LLM_API_BASE",
        "ULTRAFAST_LLM_API_KEY_ENV",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    init_database()
    client = TestClient(app)

    session_resp = client.post("/chat/sessions", json={"title": "test", "mode": "agent"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    assert secret not in session_resp.text

    chat_resp = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "我想加工金刚石CRL，Ra小于460nm",
            "use_skills": True,
        },
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert "现有任务状态未被修改" in data["assistant_message"]
    assert "严格字段格式" not in data["assistant_message"]
    assert any(item.get("event_type") == "agent_decision" for item in data["execution_trace"])
    assert data["selected_skill"] == "task_understanding"
    assert data["route_plan"]["intent"] == "skill_hint"
    assert data["evidence_gap"] is None
    assert data["audit_trace"]
    assert secret not in chat_resp.text

    messages_resp = client.get(f"/chat/sessions/{session_id}/messages")
    assert messages_resp.status_code == 200
    assert [m["role"] for m in messages_resp.json()["messages"]] == ["user", "assistant"]
    assert secret not in messages_resp.text


def test_chat_api_streaming_rejected(isolated_root):
    init_database()
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hello", "stream": True})
    assert resp.status_code == 400
    assert "streaming is not supported" in resp.text
