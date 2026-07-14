from __future__ import annotations

from ultrafast_agent.skills import load_skill_contracts
from ultrafast_domain.domain_packs import list_domain_packs, load_domain_pack
from ultrafast_domain.domain_packs.tgv import assess_aspect_ratio


def test_skill_registry_contains_only_six_composable_descriptors(project_root):
    registry = load_skill_contracts(project_root / "skills/contracts.yaml")

    assert {item.name for item in registry.list()} == {
        "task_understanding", "evidence_research", "process_planning",
        "parameter_recommendation", "experiment_optimization", "result_learning",
    }
    assert all(item.recommended_tools for item in registry.list())
    assert all(not hasattr(item, "allowed_tools") for item in registry.list())


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


def test_legacy_skill_names_resolve_at_boundary_without_new_registry_entries(project_root):
    registry = load_skill_contracts(project_root / "skills/contracts.yaml")
    assert registry.get("task_intake").name == "task_understanding"
    assert registry.get("rag_literature_retrieval").name == "evidence_research"
    assert "task_intake" not in {item.name for item in registry.list()}


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
