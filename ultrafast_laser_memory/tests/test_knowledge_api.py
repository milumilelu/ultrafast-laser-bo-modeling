from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.app.api import app
from ultrafast_memory.db.init_db import init_database


def test_knowledge_api_bootstrap_review_and_rag_flow(isolated_root):
    init_database()
    client = TestClient(app)

    gap = client.post(
        "/knowledge/evidence-gap",
        json={
            "task_spec": {"material": "diamond", "component_type": "CRL", "process_type": "femtosecond_laser_micromachining"},
            "question": "金刚石 CRL 如何进行超快激光加工？",
            "internal_hits": [],
        },
    )
    assert gap.status_code == 200
    assert gap.json()["recommended_action"] == "web_bootstrap"

    bootstrap = client.post(
        "/knowledge/bootstrap-web",
        json={
            "task_spec": {"material": "diamond", "component_type": "CRL", "process_type": "femtosecond_laser_micromachining"},
            "question": "金刚石 CRL 如何进行超快激光加工？",
            "max_sources": 1,
        },
    )
    assert bootstrap.status_code == 200
    review_id = bootstrap.json()["review_tasks"][0]["review_id"]

    tasks = client.get("/knowledge/review/tasks?status=pending_review")
    assert tasks.status_code == 200
    assert any(task["review_id"] == review_id for task in tasks.json())

    action = client.post(
        f"/knowledge/review/tasks/{review_id}/action",
        json={"action": "accept_to_rag", "reviewer_id": "expert_001", "comment": "背景知识", "target_level": "LEVEL_1_RAG_BACKGROUND"},
    )
    assert action.status_code == 200
    assert action.json()["status"] == "accepted_to_rag"

    docs = client.get("/rag/documents")
    assert docs.status_code == 200
    assert len(docs.json()) == 1
