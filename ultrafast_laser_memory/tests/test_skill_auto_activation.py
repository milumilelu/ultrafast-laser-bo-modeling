from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app


def test_skill_auto_activation(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="加工 3 mm 厚 T300 碳纤维板的 4 mm 通孔",
        message_id="auto-skill",
        client=None,
    )

    assert "task_understanding" in result["active_skills"]
    assert "parameter_recommendation" in result["active_skills"]
    assert all(item["action"] not in {"load_skill", "unload_skill"} for item in [result["final_action"]])

