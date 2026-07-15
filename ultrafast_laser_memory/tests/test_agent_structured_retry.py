import json

from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry


def test_planner_retry_actually_runs():
    class RetryLLM:
        provider = "test"
        model = "retry"

        def __init__(self):
            self.calls = []

        def chat(self, messages, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {"content": '{"action":"call_tool"}'}
            return {"content": json.dumps({"action": "final_answer", "decision_summary": "repaired", "message": "done"})}

    llm = RetryLLM()
    action = MainAgentPlanner(llm).decide(
        message="hello", working_context={"task": {}},
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )
    assert action.action == "final_answer"
    assert len(llm.calls) == 2
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in llm.calls[1]


def test_provider_actions_array_is_normalized_to_one_action():
    normalized = MainAgentPlanner._normalize_provider_action({"actions": [{
        "type": "tool_call", "tool": "search_knowledge", "args": {"query": "diamond"},
        "context_updates": {"task": {"material": {"name": "diamond"}}},
    }]}, "diamond")
    assert normalized["action"] == "call_tool"
    assert normalized["tool_name"] == "search_knowledge"
    assert normalized["context_updates"]["task"]["material"]["name"] == "diamond"


def test_single_blocking_question_is_accepted_without_retry():
    class QuestionRetryLLM:
        provider = "test"
        model = "question-retry"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            return {"content": json.dumps({
                "action": "ask_user", "decision_summary": "确认关键歧义", "message": "槽深是多少？",
            }, ensure_ascii=False)}

    llm = QuestionRetryLLM()
    action = MainAgentPlanner(llm).decide(
        message="加工矩形槽", working_context={"task": {}},
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )
    assert llm.calls == 1
    assert action.action == "ask_user"
    assert action.message == "槽深是多少？"
