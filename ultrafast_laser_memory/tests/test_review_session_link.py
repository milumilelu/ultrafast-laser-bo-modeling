from __future__ import annotations

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def test_review_action_updates_linked_chat_session_state(isolated_root):
    init_database()
    first = handle_chat(ChatRequest(message="查文献和论文解释超快激光损伤机制"))
    second = handle_chat(ChatRequest(session_id=first.session_id, message="/bootstrap run"))
    candidate_id = second.knowledge_bootstrap["candidate_ids"][0]
    review_ids = second.knowledge_bootstrap["review_task_ids"]

    state = get_session_state(first.session_id)
    assert candidate_id in state["active_knowledge_bootstrap"]["candidate_ids"]

    for review_id in review_ids:
        apply_review_action(review_id, ReviewActionRequest(action="accept_to_rag", reviewer_id="expert"))

    updated = get_session_state(first.session_id)
    assert candidate_id in updated["active_knowledge_bootstrap"]["accepted_candidate_ids"]
    assert updated["active_knowledge_bootstrap"]["status"] == "reviewed"

    status = handle_chat(ChatRequest(session_id=first.session_id, message="/bootstrap status"))
    assert "已接收入 RAG" in status.assistant_message
