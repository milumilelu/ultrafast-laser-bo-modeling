from __future__ import annotations

from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.db.init_db import init_database


def test_rag_route_requires_evidence_gap_check(isolated_root):
    init_database()

    plan = route_message("帮我查文献解释金刚石 CRL 飞秒加工", "session-rag", "message-rag")

    assert plan.primary_skill == "complex_process_task"
    assert plan.requires_evidence_gap_check is True
    assert "knowledge_bootstrap" in plan.secondary_skills


def test_bo_route_blocks_recommendation_when_evidence_is_insufficient(isolated_root):
    init_database()

    plan = route_message("请基于文献和 BO 推荐金刚石 CRL 参数", "session-bo", "message-bo")

    assert plan.requires_evidence_gap_check is True
    assert any(tool.tool == "bo_recommendation" for tool in plan.blocked_tools)


def test_bootstrap_run_manual_command_routes_to_knowledge_bootstrap(isolated_root):
    init_database()

    plan = route_message("/bootstrap run", "session-bootstrap-route", "message-bootstrap-route")

    assert plan.primary_skill == "knowledge_bootstrap"
    assert plan.requires_web_bootstrap is True
