import json

from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_memory.chat.main_agent_tools import build_main_agent_tool_registry
from ultrafast_memory.process_workflow.agent_controller import ProcessAgentController


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
    action = ProcessAgentController(llm).decide(
        message="hello", task_spec={}, business_state="INTAKE",
        context=ClarificationContext(workflow_type="task_understanding", stage="intake"),
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )
    assert action.action == "final_answer"
    assert "response_format" in llm.calls[0] and "response_format" not in llm.calls[1]
