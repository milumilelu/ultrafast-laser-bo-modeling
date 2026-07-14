from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner


def test_legacy_names_are_read_aliases_not_registered_capabilities():
    registry = get_default_skill_registry()
    assert registry.get("task_intake").name == "task_understanding"
    assert "task_intake" not in {item.name for item in registry.list()}
    action = MainAgentPlanner._validate_action(
        {"action": "call_tool", "decision_summary": "compat", "tool_name": "search_rag", "arguments": {}},
        ["search_knowledge"], [],
    )
    assert action.tool_name == "search_knowledge"
