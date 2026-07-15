from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry


def test_governance_review_tools_are_not_agent_facing():
    names = {item.name for item in build_main_agent_tool_registry().list_contracts()}
    assert "review_knowledge_candidate" not in names
    assert "create_knowledge_candidate" not in names
