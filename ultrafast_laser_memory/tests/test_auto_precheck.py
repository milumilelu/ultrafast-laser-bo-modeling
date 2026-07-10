from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_bootstrap.auto_precheck import run_auto_precheck


def test_auto_precheck_missing_source_needs_more_evidence(isolated_root):
    init_database()

    result = run_auto_precheck({"claim": "背景知识", "material": "diamond", "process_type": "fs", "usable_for": ["background"], "not_usable_for": ["BO_training"]})

    assert result["suggested_action"] == "needs_more_evidence"
    assert "missing_source_id" in result["issues"]


def test_auto_precheck_missing_material_needs_more_evidence(isolated_root):
    init_database()

    result = run_auto_precheck({"source_id": "src_1", "claim": "背景知识", "process_type": "fs", "usable_for": ["background"], "not_usable_for": ["BO_training"]})

    assert result["suggested_action"] == "needs_more_evidence"


def test_auto_precheck_parameter_claim_is_high_risk(isolated_root):
    init_database()

    result = run_auto_precheck({"source_id": "src_1", "claim": "功率 10 W", "material": "diamond", "process_type": "fs", "usable_for": ["background"], "not_usable_for": ["BO_training"]})

    assert result["risk_level"] == "high"
    assert result["suggested_action"] == "needs_more_evidence"


def test_auto_precheck_background_claim_accept_to_rag(isolated_root):
    init_database()

    result = run_auto_precheck({"source_id": "src_1", "claim": "可行性背景", "material": "diamond", "process_type": "fs", "usable_for": ["background"], "not_usable_for": ["BO_training"]})

    assert result["risk_level"] == "low"
    assert result["suggested_action"] == "accept_to_rag"
