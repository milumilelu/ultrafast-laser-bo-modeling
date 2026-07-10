from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_bootstrap.candidate_builder import build_knowledge_candidate
from ultrafast_memory.knowledge_bootstrap.source_registry import register_external_source


def test_candidate_builder_persists_traceable_candidate(isolated_root):
    init_database()
    source = register_external_source(
        {
            "title": "Mock source",
            "url": "https://example.org/source",
            "snippet": "Background evidence",
            "source_type": "paper",
            "provider": "mock_web_search",
        }
    )

    candidate = build_knowledge_candidate(
        source,
        {
            "claim": "飞秒激光可作为背景可行性证据。",
            "material": "diamond",
            "process_type": "femtosecond_laser_micromachining",
            "component_type": "CRL",
            "usable_for": ["literature_background"],
            "not_usable_for": ["BO_training"],
            "evidence_type": "web_evidence",
            "confidence": 0.6,
        },
    )

    assert candidate["candidate_id"].startswith("kc_")
    assert candidate["source_id"] == source["source_id"]
    assert candidate["review_status"] == "pending_review"
