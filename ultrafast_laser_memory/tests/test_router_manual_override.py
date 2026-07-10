from __future__ import annotations

from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def test_manual_skill_override_persists_route_trace(isolated_root):
    init_database()

    plan = route_message("/skill crl_task_planning", "session-manual", "message-manual")

    assert plan.primary_skill == "crl_task_planning"
    assert plan.route_source == "manual_override"
    assert plan.confidence == 1.0
    with get_connection() as conn:
        trace = conn.execute(
            "SELECT route_source FROM chat_route_trace WHERE session_id = ?",
            ("session-manual",),
        ).fetchone()
    assert trace["route_source"] == "manual_override"


def test_invalid_manual_skill_falls_back_to_task_intake(isolated_root):
    init_database()

    plan = route_message("/skill not_real", "session-invalid", "message-invalid")

    assert plan.primary_skill == "task_intake"
    assert plan.requires_clarification is True
    assert plan.route_source == "manual_override"
