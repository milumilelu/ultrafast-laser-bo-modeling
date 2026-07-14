from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.chat.main_agent_loop import _exposed_tool_names


def test_initial_capabilities_are_small_and_loading_reveals_tools():
    registry = get_default_skill_registry()
    initial = _exposed_tool_names(registry, [])
    loaded = _exposed_tool_names(registry, ["evidence_research"])
    assert initial == {"update_task_context", "get_equipment_context"}
    assert "search_knowledge" not in initial
    assert {"search_knowledge", "bootstrap_external_knowledge", "ingest_files"} <= loaded
