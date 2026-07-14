from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.chat.main_agent_tools import build_main_agent_tool_registry


def test_human_review_tool_cannot_run_without_human_approval():
    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "review_knowledge_candidate", {"review_id": "r", "action": "reject", "reviewer_id": "x"}, {},
    )
    assert result.error_code == "human_approval_required"
