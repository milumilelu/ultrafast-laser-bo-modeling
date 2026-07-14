from __future__ import annotations

from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.db.init_db import init_database


def test_rag_route_requires_evidence_gap_check(isolated_root):
    init_database()

    plan = route_message("帮我查文献解释金刚石 CRL 飞秒加工", "session-rag", "message-rag")

    assert plan.primary_skill == "evidence_research"
    assert plan.intent == "skill_hint"


def test_bo_route_blocks_recommendation_when_evidence_is_insufficient(isolated_root):
    init_database()

    plan = route_message("请基于文献和 BO 推荐金刚石 CRL 参数", "session-bo", "message-bo")

    assert plan.primary_skill in {"evidence_research", "experiment_optimization", "parameter_recommendation"}
    assert plan.blocked_tools == []


def test_bootstrap_run_manual_command_routes_to_knowledge_bootstrap(isolated_root):
    init_database()

    plan = route_message("/bootstrap run", "session-bootstrap-route", "message-bootstrap-route")

    assert plan.primary_skill == "evidence_research"
    assert plan.intent == "skill_hint"
