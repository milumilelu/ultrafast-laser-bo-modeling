from __future__ import annotations

from ultrafast_domain.review import ClaimClassificationService, KnowledgeUseGate, build_approval_key


EQUIPMENT = {
    "active": True,
    "revision_id": "eqrev-1",
    "machine_bounds": {"scan_speed_mm_s": [10, 1000], "laser_power_W": [1, 20]},
}


def test_deterministic_classification_enforces_numeric_recommendation_and_safety_risk():
    service = ClaimClassificationService()

    numeric = service.classify("扫描速度范围为 100-200 mm/s")
    recommendation = service.classify("推荐采用 10 W 激光功率")
    safety = service.classify("损伤阈值为 20 W")
    measurement = service.classify("使用 SEM 进行表征")

    assert numeric.claim_type == "numeric_range" and numeric.risk_level == "high"
    assert recommendation.risk_level == "high"
    assert safety.risk_level == "critical"
    assert measurement.risk_level == "low" and measurement.requires_review_before == ()


def test_background_is_allowed_but_parameter_use_requires_approval():
    evidence = [{"evidence_id": "e1", "claim": "扫描速度范围为 100-200 mm/s", "status": "pending_review"}]

    background = KnowledgeUseGate.evaluate({}, "background_explanation", evidence, {})
    parameter = KnowledgeUseGate.evaluate({}, "parameter_recommendation", evidence, EQUIPMENT)

    assert background.status.value == "allowed"
    assert parameter.status.value == "approval_required"


def test_gate_blocks_missing_equipment_rejected_evidence_and_bound_violation():
    evidence = [{"evidence_id": "e1", "claim": "功率为 25 W", "parameters": {"laser_power_W": 25}}]

    missing_equipment = KnowledgeUseGate.evaluate({}, "parameter_recommendation", evidence, {})
    violation = KnowledgeUseGate.evaluate({}, "parameter_recommendation", evidence, EQUIPMENT)
    rejected = KnowledgeUseGate.evaluate(
        {},
        "parameter_recommendation",
        [{"evidence_id": "e2", "claim": "功率为 10 W", "status": "rejected"}],
        EQUIPMENT,
    )

    assert missing_equipment.status.value == "blocked"
    assert violation.status.value == "blocked"
    assert rejected.status.value == "blocked"


def test_approval_key_changes_with_equipment_or_claim_revision():
    common = {
        "source_revision": "source-v1",
        "claim_revision": "claim-v1",
        "material": "glass",
        "material_grade": "TGV",
        "process_type": "drilling",
        "equipment_revision": "eq-v1",
        "intended_use": "parameter_recommendation",
        "conditions": {"diameter_um": 50},
    }
    original = build_approval_key(**common)
    changed_equipment = build_approval_key(**{**common, "equipment_revision": "eq-v2"})
    changed_claim = build_approval_key(**{**common, "claim_revision": "claim-v2"})

    assert original != changed_equipment
    assert original != changed_claim
