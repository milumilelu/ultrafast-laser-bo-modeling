from ultrafast_agent.skills import get_default_skill_registry


def test_skills_compose_by_recommended_tool_union_without_exclusion():
    registry = get_default_skill_registry()
    names = {"process_planning", "parameter_recommendation"}
    tools = set().union(*(set(registry.get(name).recommended_tools) for name in names))
    assert {"manage_trial", "recommend_process_parameters"} <= tools
