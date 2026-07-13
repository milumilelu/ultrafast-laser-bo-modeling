from __future__ import annotations

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def test_chat_knowledge_bootstrap_permission_and_review_flow(isolated_root):
    init_database()

    first = handle_chat(
        ChatRequest(
            message="请查文献和论文解释超快激光损伤机制",
            use_skills=True,
        )
    )

    assert first.route_plan["requires_evidence_gap_check"] is True
    assert first.evidence_gap["has_sufficient_internal_evidence"] is False
    assert "是否允许" in first.assistant_message
    assert first.knowledge_bootstrap["executed"] is False
    state = get_session_state(first.session_id)
    assert state["pending_bootstrap_permission"] is True

    second = handle_chat(ChatRequest(session_id=first.session_id, message="可以，执行外部知识冷启动", use_skills=True))

    assert second.knowledge_bootstrap["executed"] is True
    assert second.knowledge_bootstrap["created_candidates"] > 0
    assert second.knowledge_bootstrap["review_task_ids"]
    state = get_session_state(first.session_id)
    assert state["active_knowledge_bootstrap"]["candidate_ids"]
    assert state["pending_review_task_ids"]

    status = handle_chat(ChatRequest(session_id=first.session_id, message="/bootstrap status", use_skills=True))
    assert "仍待专家审核" in status.assistant_message

    review_id = second.knowledge_bootstrap["review_task_ids"][0]
    apply_review_action(review_id, ReviewActionRequest(action="accept_to_rag", reviewer_id="expert_001"))
    updated = get_session_state(first.session_id)
    assert updated["active_knowledge_bootstrap"]["accepted_rag_doc_ids"]

    guarded = handle_chat(ChatRequest(session_id=first.session_id, message="继续生成方案", use_skills=True))
    assert "未审核候选" in guarded.assistant_message
