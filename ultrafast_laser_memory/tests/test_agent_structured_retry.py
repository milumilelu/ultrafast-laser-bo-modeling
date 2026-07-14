import json

from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry


class RetryLLM:
    provider = "test"
    model = "retry"

    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {"content": "{}"}
        return {"content": json.dumps({"action": "final_answer", "decision_summary": "ok", "skill_name": None,
                                       "tool_name": None, "arguments": {}, "message": "ok"})}


def test_invalid_structured_action_retries_once_without_schema_mode():
    llm = RetryLLM()
    action = MainAgentPlanner(llm).decide(
        message="hello", task_spec={}, business_state="INTAKE",
        context=ClarificationContext(workflow_type="task_understanding", stage="intake"),
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )
    assert action.action == "final_answer"
    assert "response_format" in llm.calls[0] and "response_format" not in llm.calls[1]
    assert llm.calls[0]["response_format"] == {"type": "json_object"}


def test_deepseek_actions_array_is_normalized_to_one_safe_action():
    class DeepSeekVariant:
        provider = "deepseek"
        model = "deepseek-v4-flash"

        def chat(self, messages, **kwargs):
            return {"content": json.dumps({"actions": [
                {"type": "tool_call", "tool": "update_task_context", "arguments": {
                    "updates": {"material": "碳纤维复合板", "thickness": "2mm"}
                }},
                {"type": "load_skill", "skill": "task_understanding"},
            ]}, ensure_ascii=False)}

    action = MainAgentPlanner(DeepSeekVariant()).decide(
        message="切割2mm厚的碳纤维复合板",
        task_spec={},
        business_state="INTAKE",
        context=ClarificationContext(workflow_type="task_understanding", stage="INTAKE"),
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )

    assert action.action == "call_tool"
    assert action.tool_name == "update_task_context"
    assert [item["field_name"] for item in action.arguments["updates"]] == [
        "material", "thickness_mm", "process_type",
    ]


def test_generic_llm_evidence_is_replaced_only_with_literal_user_evidence():
    normalized = MainAgentPlanner._normalize_provider_action({
        "action": "call_tool",
        "tool_name": "update_task_context",
        "arguments": {"updates": [
            {"field_name": "material", "value": "碳纤维复合板", "evidence": "用户原文"},
            {"field_name": "thickness_mm", "value": "2", "unit": "mm", "evidence": "用户原文"},
            {"field_name": "process_type", "value": "切割", "evidence": "用户原文"},
        ]},
    }, "切割2mm厚的碳纤维复合板")

    assert [item["evidence"] for item in normalized["arguments"]["updates"]] == [
        "碳纤维复合板", "2mm", "切割",
    ]
