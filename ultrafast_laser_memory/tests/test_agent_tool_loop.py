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


def test_semantically_repeated_task_update_stops_with_success(isolated_root):
    class RepeatingDeepSeek:
        provider = "deepseek"
        model = "deepseek-v4-flash"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            arguments = ({"updates": {
                    "material": "碳纤维复合板",
                    "thickness": "2mm",
                    "process": "切割",
                }} if self.calls == 1 else {"updates": [
                    {"field_name": "material", "value": "碳纤维复合板", "evidence": "用户原文"},
                    {"field_name": "thickness_mm", "value": 2, "unit": "mm", "evidence": "用户原文"},
                    {"field_name": "process_type", "value": "切割", "evidence": "用户原文"},
                ]})
            update = {"type": "tool_call", "tool": "update_task_context", "arguments": arguments}
            return {"content": json.dumps({"actions": [update]}, ensure_ascii=False)}

    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="切割2mm厚的碳纤维复合板",
        message_id="m-repeat",
        client=RepeatingDeepSeek(),
    )

    assert result["task_spec"] == {
        "material": "CFRP", "thickness_mm": 2.0, "process_type": "cutting",
    }
    assert result["final_action"]["action"] == "final_answer"
    assert len(result["tool_calls"]) == 1
    assert "未经验证的工艺参数" in result["content"]
