import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn


class LoopLLM:
    provider = "test"
    model = "loop"

    def __init__(self):
        self.index = 0

    def chat(self, messages, **kwargs):
        self.index += 1
        actions = [
            {"action": "load_skill", "decision_summary": "需要参数能力", "skill_name": "parameter_recommendation",
             "tool_name": None, "arguments": {}, "message": None},
            {"action": "call_tool", "decision_summary": "先读取设备", "skill_name": None,
             "tool_name": "get_equipment_context", "arguments": {}, "message": None},
            {"action": "final_answer", "decision_summary": "已获得观察", "skill_name": None,
             "tool_name": None, "arguments": {}, "message": "完成"},
        ]
        return {"content": json.dumps(actions[self.index - 1], ensure_ascii=False)}


def test_agent_runs_load_tool_observation_answer_loop(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(session_id=session_id, message="读取设备后建议参数", message_id="m", client=LoopLLM())
    assert result["active_skills"] == ["parameter_recommendation"]
    assert result["tool_calls"][0]["result"]["tool_name"] == "get_equipment_context"
    assert result["content"] == "完成"


def test_cfrp_task_updates_context_without_state_tool(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="切割2mm厚的碳纤维复合板",
        message_id="m-repeat",
        client=None,
    )

    assert result["task_spec"] == {
        "material": {"name": "CFRP", "description": "碳纤维复合板"},
        "process_intent": "cutting",
        "geometry": {"feature_type": "sheet_cut", "workpiece_thickness_mm": 2.0},
    }
    assert result["final_action"]["action"] == "final_answer"
    assert result["tool_calls"] == []
    assert "激光功率" in result["content"]
