from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_from_web


def test_bootstrap_from_web_creates_sources_candidates_review_tasks_without_rag(isolated_root):
    init_database()

    response = bootstrap_from_web(
        BootstrapWebRequest(
            task_spec={"material": "diamond", "component_type": "CRL", "process_type": "femtosecond_laser_micromachining"},
            question="金刚石 CRL 如何进行超快激光加工？",
            max_sources=3,
        )
    )

    assert response.sources
    assert response.knowledge_candidates
    assert response.review_tasks
    assert response.auto_indexed == []
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM external_source_artifact").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM knowledge_candidate").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM knowledge_review_task").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM rag_document").fetchone()[0] == 0
