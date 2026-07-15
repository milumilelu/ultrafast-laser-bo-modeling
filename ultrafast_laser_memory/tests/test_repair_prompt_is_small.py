import json

from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry


def test_repair_prompt_is_small():
    class InvalidActionLLM:
        provider = "fixture"
        model = "small-repair"

        def __init__(self):
            self.prompts = []

        def chat(self, messages, **kwargs):
            self.prompts.append(sum(len(item["content"]) for item in messages))
            return {"content": json.dumps({
                "action": "call_tool", "tool_name": "bad_name", "arguments": [],
            })}

    llm = InvalidActionLLM()
    MainAgentPlanner(llm).decide(
        message="T300 CFRP through-hole task",
        working_context={"task": {"material": {"name": "CFRP"}}},
        available_tools=build_main_agent_tool_registry().schemas_for_agent(),
    )

    assert len(llm.prompts) == 2
    assert llm.prompts[1] < llm.prompts[0] / 2
    assert llm.prompts[1] < 2_000

