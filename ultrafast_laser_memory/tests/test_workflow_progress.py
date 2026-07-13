from __future__ import annotations

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.chat.workflow_status import get_latest_progress, mark_workflow_completed
from ultrafast_memory.db.init_db import init_database


def test_new_session_progress_is_empty_or_started(isolated_root):
    init_database()

    assert get_latest_progress("new-session") is None


def test_task_intake_progress_after_chat(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="我想加工金刚石CRL，Ra小于460nm", use_skills=True))

    assert response.progress["progress_percent"] == 0
    assert response.current_stage == "REQUIREMENTS_PENDING"
    assert response.workflow_state["missing_slots"]
    assert response.workflow_state["clarification_round"] <= 3


def test_clarification_round_one_progress_percent(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="我想加工普通任务", use_skills=True))

    assert response.progress["current_stage"] in {"REQUIREMENTS_PENDING", "clarification_round_1", "task_spec_confirmed", "intake_started"}
    if response.progress["current_stage"] == "clarification_round_1":
        completed = len(response.progress["completed_steps"])
        total = completed + len(response.progress["pending_steps"])
        assert response.progress["progress_percent"] == round(completed / total * 100, 2)


def test_workflow_completed_progress_is_100(isolated_root):
    init_database()

    progress = mark_workflow_completed("session-progress")

    assert progress["progress_percent"] == 100


def test_max_clarification_round_stops_infinite_questions(isolated_root):
    init_database()
    first = handle_chat(ChatRequest(message="我想加工金刚石", use_skills=True))
    second = handle_chat(ChatRequest(session_id=first.session_id, message="还是金刚石", use_skills=True))
    third = handle_chat(ChatRequest(session_id=first.session_id, message="还是金刚石，暂时没有设备参数", use_skills=True))

    assert third.workflow_state["clarification_round"] == 3
    assert "已完成 3 轮澄清" in third.assistant_message
    assert "不能进入确定性 BO 参数推荐" in third.assistant_message
