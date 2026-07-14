from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.init_db import init_database


def test_chat_stream_ndjson_returns_route_and_delta_events(isolated_root, monkeypatch):
    for key in (
        "ULTRAFAST_LLM_PROVIDER",
        "ULTRAFAST_LLM_MODEL",
        "ULTRAFAST_LLM_API_BASE",
        "ULTRAFAST_LLM_API_KEY_ENV",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    init_database()
    client = TestClient(app)

    response = client.post(
        "/chat/stream_ndjson",
        json={"message": "我想加工金刚石 CRL，Ra小于460nm", "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["type"] for event in events][:2] == ["meta", "progress"]
    assert events[2]["type"] in {"thinking_status", "agent_trace"}
    assert "route" in [event["type"] for event in events]
    assert "trace" in [event["type"] for event in events]
    assert any(event["type"] == "delta" for event in events)
    assert events[-1]["type"] == "done"
    route = next(event for event in events if event["type"] == "route")
    assert route["primary_skill"] == "task_understanding"
    assert route["route_source"] in {"rule_router", "hybrid_router"}
    assert "api_key" not in response.text.lower()
