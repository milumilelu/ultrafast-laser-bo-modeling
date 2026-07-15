from ultrafast_memory.agent_runtime.capability_discovery import exposed_tool_names
from ultrafast_memory.agent_runtime.skill_registry import build_skill_registry


def test_composite_parameter_tool():
    visible = exposed_tool_names(build_skill_registry(), ["parameter_recommendation"])

    assert "recommend_process_parameters" in visible
    assert "recommend_parameters_bo" not in visible
    assert "recommend_parameters_rag" not in visible
    assert "propose_exploratory_parameters" not in visible

