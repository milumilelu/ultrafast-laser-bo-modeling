from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner


def test_legacy_names_are_rejected():
    registry = get_default_skill_registry()
    with pytest.raises(KeyError, match="skill not registered"):
        registry.get("task_intake")
    for old_name, current_name in (
        ("update_task_spec", "update_task_context"),
        ("get_equipment_profile", "get_equipment_context"),
        ("search_rag", "search_knowledge"),
        ("run_bo_recommendation", "recommend_parameters_bo"),
    ):
        with pytest.raises(ValueError, match="tool_not_registered"):
            MainAgentPlanner._validate_action(
                {"action": "call_tool", "decision_summary": "invalid", "tool_name": old_name, "arguments": {}},
                [current_name], [],
            )
    with pytest.raises(ValueError):
        MainAgentPlanner._validate_action(
            {"action": "direct_answer", "decision_summary": "invalid", "message": "no"},
            [], [],
        )
import pytest
