import json

from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry


class InvalidActionLLM:
    provider = "fixture"
    model = "invalid-action"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return {"content": json.dumps({
            "action": "call_tool",
            "decision_summary": "先推荐参数",
            "tool_name": "recommend_parameters",
            "arguments": [],
        }, ensure_ascii=False)}


def test_planner_validation_fallback():
    llm = InvalidActionLLM()
    events = []
    action = MainAgentPlanner(llm).decide(
        message="我想加工 3 mm 厚的 T300 碳纤维板，开一个 4 mm 通孔。",
        working_context={"task": {"material": {"name": "CFRP", "grade": "T300"}}},
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
        model_call_sink=events.append,
    )

    assert llm.calls == 2
    assert action.action == "call_tool"
    assert action.tool_name == "get_equipment_context"
    assert action.error_details == [{
        "loc": "arguments",
        "type": "dict_type",
        "msg": "Input should be a valid dictionary",
        "received": [],
        "expected": "object",
    }]
    failures = [item for item in events if item["event_type"] == "model_call_failed"]
    assert failures[-1]["parsed_action"]["arguments"] == []
    assert failures[-1]["action_schema_version"]
    assert failures[-1]["tool_registry_version"]

