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
            {"action": "call_tool", "decision_summary": "先读取设备",
             "tool_name": "get_equipment_context", "arguments": {}, "message": None},
            {"action": "final_answer", "decision_summary": "已获得观察",
             "tool_name": None, "arguments": {}, "message": "完成"},
        ]
        return {"content": json.dumps(actions[self.index - 1], ensure_ascii=False)}


def test_agent_activates_skill_without_extra_model_round(isolated_root):
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    llm = LoopLLM()
    result = run_main_agent_turn(
        session_id=session_id, message="读取设备后建议参数", message_id="m", client=llm,
        suggested_skills=["parameter_recommendation"],
    )
    assert "parameter_recommendation" in result["active_skills"]
    assert llm.index == 2
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
        "workpiece": {"thickness_mm": 2.0},
        "process_intent": "cutting",
        "geometry": {"feature_type": "sheet_cut"},
    }
    assert result["final_action"]["action"] == "final_answer"
    assert result["tool_calls"] == []
    assert "模型当前不可用" in result["content"]
