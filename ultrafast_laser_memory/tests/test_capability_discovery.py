from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.agent_runtime.main_agent_loop import _exposed_tool_names


def test_all_foreground_safe_tools_are_visible_independent_of_skills():
    registry = get_default_skill_registry()
    initial = _exposed_tool_names(registry, [])
    loaded = _exposed_tool_names(registry, ["evidence_research"])
    assert initial == loaded
    assert {"get_equipment_context", "search_knowledge", "recommend_parameters_bo",
            "recommend_parameters_rag", "propose_exploratory_parameters", "manage_trial",
            "manage_process", "record_process_result"} == initial
