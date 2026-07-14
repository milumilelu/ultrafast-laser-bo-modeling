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

    assert response.progress["progress_percent"] == 100
    assert response.current_stage == "task_spec_confirmed"
    assert response.next_required_action["action_type"] == "continue_workflow"
    assert response.workflow_state["clarification_round"] <= 3


def test_clarification_round_one_progress_percent(isolated_root):
    init_database()

    response = handle_chat(ChatRequest(message="我想加工普通任务", use_skills=True))

    assert response.progress["current_stage"] == "task_spec_confirmed"
    assert response.progress["progress_percent"] == 100
    assert response.next_required_action["action_type"] == "continue_workflow"
    if response.progress["current_stage"] == "clarification_round_1":
        completed = len(response.progress["completed_steps"])
        total = completed + len(response.progress["pending_steps"])
        assert response.progress["progress_percent"] == round(completed / total * 100, 2)


def test_workflow_completed_progress_is_100(isolated_root):
    init_database()

    progress = mark_workflow_completed("session-progress")

    assert progress["progress_percent"] == 100


def test_legacy_projection_reuses_canonical_session_task_spec(isolated_root):
    init_database()
    first = handle_chat(ChatRequest(message="我想加工金刚石 CRL", use_skills=False))
    second = handle_chat(
        ChatRequest(session_id=first.session_id, message="允许", use_skills=False)
    )

    assert first.workflow_state["task_spec"]["material"] == "diamond"
    assert second.workflow_state["task_spec"] == first.workflow_state["task_spec"]


def test_llm_failure_keeps_state_without_parser_stall(isolated_root):
    init_database()
    first = handle_chat(ChatRequest(message="我想加工金刚石", use_skills=True))
    handle_chat(ChatRequest(session_id=first.session_id, message="还是金刚石", use_skills=True))
    third = handle_chat(ChatRequest(session_id=first.session_id, message="还是金刚石，暂时没有设备参数", use_skills=True))

    assert third.workflow_state["clarification_round"] <= 3
    assert third.workflow_state["current_stage_code"] == "task_spec_confirmed"
    assert third.workflow_state["task_spec"]["material"] == "diamond"
    assert "现有任务状态未被修改" in third.assistant_message
    assert "严格字段格式" not in third.assistant_message
