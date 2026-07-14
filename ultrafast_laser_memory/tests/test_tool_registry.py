from ultrafast_memory.chat.main_agent_tools import (
    CORE_TOOL_NAMES, ON_DEMAND_TOOL_NAMES, build_main_agent_tool_registry,
)


def test_tool_registry_has_twelve_core_and_two_on_demand_tools():
    registry = build_main_agent_tool_registry()
    assert len(CORE_TOOL_NAMES) == 12
    assert len(ON_DEMAND_TOOL_NAMES) == 2
    assert {item.name for item in registry.list_contracts()} == set(CORE_TOOL_NAMES + ON_DEMAND_TOOL_NAMES)
