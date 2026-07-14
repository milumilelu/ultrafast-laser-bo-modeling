from __future__ import annotations

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def test_chat_service_persists_messages_and_skill_trace(isolated_root, monkeypatch):
    monkeypatch.delenv("ULTRAFAST_LLM_PROVIDER", raising=False)
    init_database()

    response = handle_chat(ChatRequest(message="我想加工金刚石 CRL，Ra小于460nm", use_skills=True))

    assert response.session_id
    assert "现有任务状态未被修改" in response.assistant_message
    assert "严格字段格式" not in response.assistant_message
    assert response.selected_skill == "complex_process_task"
    assert [step["step"] for step in response.audit_trace] == ["hybrid_router"]
    assert response.evidence_gap is None

    with get_connection() as conn:
        messages = conn.execute(
            "SELECT role, content FROM chat_message WHERE session_id = ? ORDER BY created_at",
            (response.session_id,),
        ).fetchall()
        assert [row["role"] for row in messages] == ["user", "assistant"]
        trace = conn.execute(
            "SELECT selected_skill FROM chat_skill_trace WHERE session_id = ?",
            (response.session_id,),
        ).fetchone()
        assert trace["selected_skill"] == "complex_process_task"
