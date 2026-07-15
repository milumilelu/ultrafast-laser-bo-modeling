from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_from_web
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest
from ultrafast_memory.rag.query_service import query_rag


def test_accept_to_rag_builds_real_searchable_chunk_and_index_entry(isolated_root):
    init_database()
    response = bootstrap_from_web(BootstrapWebRequest(task_spec={"material": "diamond", "component_type": "CRL"}, question="金刚石 CRL", max_sources=1))

    result = apply_review_action(
        response.review_tasks[0]["review_id"],
        ReviewActionRequest(action="accept_to_rag", reviewer_id="expert"),
    )

    with get_connection() as conn:
        doc = conn.execute("SELECT * FROM rag_document").fetchone()
        job = conn.execute("SELECT * FROM rag_index_job").fetchone()
        chunk = conn.execute("SELECT * FROM literature_chunk").fetchone()
        entry = conn.execute("SELECT * FROM rag_index_entry").fetchone()
    assert "审核状态：accepted_to_rag" in doc["content"]
    assert doc["indexed"] == 1
    assert doc["index_name"] == "literature_default"
    assert job["status"] == "success"
    assert chunk["chunk_id"] == result["index_job"]["canonical_document"]["chunk_id"]
    assert chunk["review_status"] == "accepted"
    assert entry["chunk_id"] == chunk["chunk_id"]
    assert entry["status"] == "indexed"

    pack = query_rag({"query": "diamond CRL", "purpose": "literature_background"})
    assert any(hit["chunk_id"] == chunk["chunk_id"] for hit in pack["hits"])
    assert any(hit["authority_level"] == "reviewed_background" for hit in pack["hits"])
