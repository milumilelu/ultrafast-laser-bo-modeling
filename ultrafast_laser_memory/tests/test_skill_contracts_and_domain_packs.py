from __future__ import annotations

from ultrafast_agent.skills import load_skill_contracts
from ultrafast_domain.domain_packs import list_domain_packs, load_domain_pack
from ultrafast_domain.domain_packs.tgv import assess_aspect_ratio


def test_all_skill_contracts_validate_and_forbid_direct_database(project_root):
    registry = load_skill_contracts(project_root / "skills/contracts.yaml")

    assert len(registry.list()) >= 40
    assert registry.get("bo_recommendation").preconditions == (
        "equipment_gate_allowed",
        "knowledge_gate_allowed",
    )
    for contract in registry.list():
        assert not ({"sqlite", "database_connection", "raw_sql"} & set(contract.allowed_tools))


def test_legacy_router_skills_have_contracts(project_root):
    from ultrafast_memory.chat.router.rule_router import rule_route

    registry = load_skill_contracts(project_root / "skills/contracts.yaml")
    messages = [
        "导入日志",
        "导出 BO 数据",
        "请用 BO 推荐参数",
        "金刚石 CRL",
        "查文献",
        "更新经验",
        "生成报告",
    ]
    for message in messages:
        route = rule_route(message, {})
        assert route is not None
        assert registry.get(route.primary_skill)


def test_crl_compatibility_contract_emits_deprecation_event(project_root):
    registry = load_skill_contracts(project_root / "skills/contracts.yaml")
    contract = registry.get("crl_task_planning")

    assert "deprecated_skill_used" in contract.emitted_events
    assert "optical_component_task_workflow" in contract.allowed_tools

    from ultrafast_memory.chat.router.rule_router import rule_route

    route = rule_route("规划金刚石 CRL", {})
    assert route.deprecated_skill_used is True
    assert route.replacement_skill == "optical_component_task_workflow"
    assert route.emitted_events == ["deprecated_skill_used"]


def test_domain_pack_registry_and_crl_specific_capabilities():
    names = [pack.name for pack in list_domain_packs()]
    crl = load_domain_pack("crl")

    assert names == ["cover_glass", "crl", "film_cooling_hole", "surface_texturing", "tgv"]
    assert "wavefront_error" in crl.quality_metrics
    assert "focal_spot_size_um" in crl.quality_metrics
    assert crl.trial_templates["simple_trial_cut"]["representative_geometry"] == "shallow_paraboloid_segment_or_scaled_lens"
    assert crl.validate_geometry({"radius_um": 50, "aperture_um": 300, "lens_count": 10, "surface_count": 2})["valid"] is True


def test_tgv_pack_calculates_aspect_ratio():
    result = assess_aspect_ratio({"wafer_thickness_um": 500, "hole_diameter_um": 50})

    assert result["aspect_ratio"] == 10
    assert result["high_aspect_ratio"] is True
