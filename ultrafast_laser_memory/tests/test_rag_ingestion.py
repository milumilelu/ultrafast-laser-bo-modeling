from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_from_web
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def test_accept_to_rag_builds_document_and_index_job(isolated_root):
    init_database()
    response = bootstrap_from_web(BootstrapWebRequest(task_spec={"material": "diamond", "component_type": "CRL"}, question="金刚石 CRL", max_sources=1))

    apply_review_action(response.review_tasks[0]["review_id"], ReviewActionRequest(action="accept_to_rag", reviewer_id="expert"))

    with get_connection() as conn:
        doc = conn.execute("SELECT * FROM rag_document").fetchone()
        job = conn.execute("SELECT * FROM rag_index_job").fetchone()
    assert "审核状态：accepted_to_rag" in doc["content"]
    assert doc["indexed"] == 1
    assert job["status"] == "success"
