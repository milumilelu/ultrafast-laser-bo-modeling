from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app


def test_trace_failure_does_not_break_chat(isolated_root, monkeypatch):
    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.main_agent_loop.record_agent_trace_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("trace unavailable")),
    )
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="加工 3 mm 厚 T300 碳纤维板的 4 mm 通孔",
        message_id="trace-failure",
        client=None,
    )

    assert result["final_action"]["action"] == "respond"
    assert "NextAction" in result["content"]

