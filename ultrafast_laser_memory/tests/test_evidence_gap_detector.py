from __future__ import annotations

from ultrafast_memory.knowledge_bootstrap.evidence_gap_detector import detect_evidence_gap


def test_evidence_gap_empty_hits_requires_web_bootstrap():
    result = detect_evidence_gap("金刚石 CRL 如何加工？", {"material": "diamond", "component_type": "CRL"}, [])

    assert result["recommended_action"] == "web_bootstrap"
    assert result["evidence_score"] == 0.0
    assert "diamond_CRL_literature" in result["missing_evidence"]


def test_evidence_gap_few_hits_stays_low():
    result = detect_evidence_gap("question", {"material": "diamond"}, [{"material": "diamond", "source_id": "src_1"}])

    assert result["evidence_score"] <= 0.4


def test_evidence_gap_material_mismatch_penalizes_score():
    matched = detect_evidence_gap(
        "question",
        {"material": "diamond", "process_type": "femtosecond_laser_micromachining"},
        [
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_1"},
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_2"},
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_3"},
        ],
    )
    mismatched = detect_evidence_gap(
        "question",
        {"material": "diamond", "process_type": "femtosecond_laser_micromachining"},
        [
            {"material": "silicon", "process_type": "milling", "source_id": "src_1"},
            {"material": "silicon", "process_type": "milling", "source_id": "src_2"},
            {"material": "silicon", "process_type": "milling", "source_id": "src_3"},
        ],
    )

    assert mismatched["evidence_score"] < matched["evidence_score"]


def test_evidence_gap_high_quality_hits_answer_from_internal():
    result = detect_evidence_gap(
        "question",
        {"material": "diamond", "process_type": "femtosecond_laser_micromachining"},
        [
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_1"},
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_2"},
            {"material": "diamond", "process_type": "femtosecond_laser_micromachining", "source_id": "src_3"},
        ],
    )

    assert result["recommended_action"] == "answer_from_internal"
