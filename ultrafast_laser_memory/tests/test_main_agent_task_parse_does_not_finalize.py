from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app


def test_main_agent_task_parse_does_not_finalize(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="我想加工 3 mm 厚的 T300 碳纤维板，开一个 4 mm 通孔。",
        message_id="parse-does-not-finalize",
        client=None,
    )

    assert result["task_spec"]["material"] == {
        "name": "CFRP", "description": "碳纤维板", "grade": "T300",
    }
    assert result["task_spec"]["workpiece"]["thickness_mm"] == 3
    assert result["task_spec"]["geometry"]["dimensions"]["diameter_mm"] == 4
    assert result["tool_calls"][0]["tool_name"] == "get_equipment_context"
    assert result["final_action"]["action"] == "respond"

