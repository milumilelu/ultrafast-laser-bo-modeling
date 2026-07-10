from __future__ import annotations

from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.db.init_db import init_database


def test_hybrid_router_marks_ambiguous_rule_candidate(isolated_root, monkeypatch):
    monkeypatch.delenv("ULTRAFAST_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ULTRAFAST_LLM_MODEL", raising=False)
    monkeypatch.delenv("ULTRAFAST_LLM_API_BASE", raising=False)
    monkeypatch.delenv("ULTRAFAST_LLM_API_KEY_ENV", raising=False)
    init_database()

    plan = route_message("这次失败了，粗糙度没到，想让 BO 做下一轮优化", "session-hybrid", "message-hybrid")

    assert plan.primary_skill == "experience_memory_update"
    assert "bo_recommendation" in plan.secondary_skills
    assert plan.route_source == "hybrid_router"
    assert plan.requires_clarification is True
