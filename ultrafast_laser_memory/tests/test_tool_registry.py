from ultrafast_memory.agent_runtime.tool_registry import (
    CORE_TOOL_NAMES, ON_DEMAND_TOOL_NAMES, build_main_agent_tool_registry,
)


def test_tool_registry_has_eight_foreground_and_three_on_demand_tools():
    registry = build_main_agent_tool_registry()
    assert len(CORE_TOOL_NAMES) == 8
    assert len(ON_DEMAND_TOOL_NAMES) == 3
    assert {item.name for item in registry.list_contracts()} == set(CORE_TOOL_NAMES + ON_DEMAND_TOOL_NAMES)
