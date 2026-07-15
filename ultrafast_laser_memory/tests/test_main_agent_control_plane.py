from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.chat.session_state import get_session_state


def _session() -> str:
    return TestClient(app).post("/chat/sessions", json={}).json()["session_id"]


def test_diamond_through_hole_uses_open_geometry_and_persists(isolated_root):
    session_id = _session()
    result = run_main_agent_turn(
        session_id=session_id, message="在4mm厚的金刚石上加工一个直径2mm的通孔",
        message_id="diamond", client=None,
    )
    task = result["task_spec"]
    assert task["material"]["name"] == "diamond"
    assert task["material"]["thickness_mm"] == 4
    assert task["process_intent"] == "hole_drilling"
    assert task["geometry"] == {"feature_type": "through_hole", "dimensions": {"diameter_mm": 2.0}, "through": True}
    assert "cut_length_mm" not in task and "layer_cut_allowed" not in task
    assert get_session_state(session_id)["working_context_json"]["task"] == task


def test_router_is_only_a_hint(isolated_root):
    plan = route_message("在4mm厚的金刚石上加工一个直径2mm的通孔", "route", "message")
    assert plan.primary_skill == "task_understanding"
    assert plan.route_source != "mandatory_process_rule"
    assert "state_update" not in plan.model_dump()
