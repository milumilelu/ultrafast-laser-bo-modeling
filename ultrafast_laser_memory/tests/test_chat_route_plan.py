from __future__ import annotations

import json

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def test_chat_response_includes_route_plan_and_trace(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="读取 recipe 和 log 日志", use_skills=True))

    assert response.selected_skill == "process_file_ingestion"
    assert response.route_plan is not None
    assert response.route_plan["primary_skill"] == "process_file_ingestion"
    with get_connection() as conn:
        trace = conn.execute(
            "SELECT route_plan_json FROM chat_route_trace WHERE session_id = ?",
            (response.session_id,),
        ).fetchone()
    persisted = json.loads(trace["route_plan_json"])
    assert persisted["primary_skill"] == "process_file_ingestion"
