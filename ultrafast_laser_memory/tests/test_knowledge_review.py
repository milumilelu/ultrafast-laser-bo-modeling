from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_from_web
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def _review_id():
    response = bootstrap_from_web(
        BootstrapWebRequest(
            task_spec={"material": "diamond", "component_type": "CRL"},
            question="金刚石 CRL",
            max_sources=1,
        )
    )
    return response.review_tasks[0]["review_id"]


def test_review_reject_updates_candidate_and_task(isolated_root):
    init_database()
    review_id = _review_id()

    result = apply_review_action(review_id, ReviewActionRequest(action="reject", reviewer_id="expert", comment="不采用"))

    assert result["status"] == "rejected"
    with get_connection() as conn:
        task = conn.execute("SELECT review_status FROM knowledge_review_task WHERE review_id = ?", (review_id,)).fetchone()
        candidate = conn.execute("SELECT status, review_status FROM knowledge_candidate WHERE candidate_id = ?", (result["candidate_id"],)).fetchone()
        action_count = conn.execute("SELECT COUNT(*) FROM knowledge_review_action WHERE review_id = ?", (review_id,)).fetchone()[0]
    assert task["review_status"] == "rejected"
    assert candidate["status"] == "rejected"
    assert candidate["review_status"] == "rejected"
    assert action_count == 1


def test_review_needs_more_evidence_updates_status(isolated_root):
    init_database()
    review_id = _review_id()

    result = apply_review_action(review_id, ReviewActionRequest(action="needs_more_evidence", reviewer_id="expert"))

    assert result["status"] == "needs_more_evidence"


def test_review_accept_to_rag_indexes_without_bo_or_prior(isolated_root):
    init_database()
    review_id = _review_id()

    result = apply_review_action(review_id, ReviewActionRequest(action="accept_to_rag", reviewer_id="expert", target_level="LEVEL_1_RAG_BACKGROUND"))

    assert result["status"] == "accepted_to_rag"
    assert result["rag_document"]["rag_doc_id"]
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rag_document").fetchone()[0] == 1
        assert conn.execute("SELECT indexed FROM rag_document").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM process_prior").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM validated_rule").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM bo_training_sample").fetchone()[0] == 0


def test_review_accept_as_literature_evidence_writes_evidence_and_rag(isolated_root):
    init_database()
    review_id = _review_id()

    result = apply_review_action(review_id, ReviewActionRequest(action="accept_as_literature_evidence", reviewer_id="expert"))

    assert result["status"] == "accepted_as_literature_evidence"
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM literature_evidence").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM rag_document").fetchone()[0] == 1
