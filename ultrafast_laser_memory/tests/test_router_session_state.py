from __future__ import annotations

from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.db.init_db import init_database


def test_router_uses_session_state_for_clarification_continuation(isolated_root):
    init_database()
    session_id = "session-continuation"

    first = route_message("我想加工金刚石 CRL，Ra小于460nm", session_id, "message-1")
    state = get_session_state(session_id)
    second = route_message("单晶，1030 nm，300 fs，允许后处理", session_id, "message-2")

    assert first.primary_skill == "crl_task_planning"
    assert first.requires_clarification is True
    assert state["active_skill"] == "crl_task_planning"
    assert state["pending_questions"]
    assert second.primary_skill == "crl_task_planning"
    assert second.route_source == "session_state"
