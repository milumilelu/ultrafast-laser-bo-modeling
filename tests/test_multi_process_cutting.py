from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from src.features import add_engineered_features
from src.interface import validate_feedback
from src.interactive_bo import init_task, load_task_state, recommend_next, recommend_parameters, submit_feedback
from src.schema import model_status_from_sample_count, normalize_fill_pattern, normalize_process_type


def _config(tmp_path: Path) -> dict:
    root = tmp_path
    (root / "data" / "processed").mkdir(parents=True)
    (root / "outputs").mkdir()
    rows = []
    for i in range(18):
        d_proxy = [0.06, 0.12, 0.24, 0.48, 0.72, 1.0][i % 6]
        speed = [50, 80, 120][i % 3]
        spacing = [4, 6][i % 2]
        passes = max(1, int(round(d_proxy * speed * spacing / 20)))
        frequency = d_proxy * speed * spacing / passes
        rows.append(
            {
                "record_id": f"milling-{i}",
                "process_type": "milling",
                "material": "SiC",
                "pulse_width_ps": [0.5, 1.0, 2.0][i % 3],
                "frequency_kHz": frequency,
                "hatch_spacing_um": spacing,
                "passes": passes,
                "scan_speed_mm_s": speed,
                "laser_power_W": None,
                "depth_um": 8 + 18 * d_proxy + (i % 3),
                "Sa_um": 0.4 + 2.2 * d_proxy,
                "valid_flag": True,
                "source_file": "synthetic",
                "note": "",
            }
        )
    df = add_engineered_features(pd.DataFrame(rows))
    featured = root / "data" / "processed" / "unified_experiments_with_features.csv"
    updated = root / "data" / "processed" / "updated_experiments.csv"
    df.to_csv(featured, index=False)
    shutil.copy(featured, updated)
    return {"_root": str(root), "output_dir": str(root / "outputs"), "random_seed": 42, "bo_candidate_grid_size": 250, "lambda_sa": 0.25}


def _cutting_bounds() -> dict:
    return {
        "pulse_width_ps": [0.3, 10],
        "frequency_kHz": [50, 500],
        "laser_power_W": [1, 20],
        "scan_speed_mm_s": [10, 1000],
        "passes": [1, 30],
        "focus_offset_um": [-100, 100],
        "layer_step_um": [1, 20],
        "hatch_spacing_um": [1, 20],
        "fill_pattern": ["none", "contour", "polyline"],
    }


def _state_path(cfg: dict, task_id: str) -> Path:
    return Path(cfg["output_dir"]) / "tasks" / f"{task_id}_task_state.json"


def test_process_type_defaults_to_milling():
    assert normalize_process_type(None) == "milling"
    assert normalize_process_type("铣削") == "milling"
    assert normalize_process_type("切割") == "cutting"


def test_fill_pattern_chinese_mapping():
    assert normalize_fill_pattern("弓字形") == "zigzag"
    assert normalize_fill_pattern("回字形/轮廓") == "contour"
    assert normalize_fill_pattern("同心圆") == "concentric"
    assert normalize_fill_pattern("折线") == "polyline"
    assert normalize_fill_pattern("无填充/单线切割") == "none"
    assert normalize_fill_pattern("自定义") == "custom"


def test_power_feature_engineering_units():
    out = add_engineered_features(
        pd.DataFrame(
            {
                "laser_power_W": [2.0],
                "frequency_kHz": [100.0],
                "scan_speed_mm_s": [10.0],
                "hatch_spacing_um": [5.0],
                "passes": [2.0],
                "pulse_width_ps": [1.0],
                "target_depth_um": [100.0],
                "layer_step_um": [10.0],
            }
        )
    )
    assert out.loc[0, "pulse_energy_uJ"] == 20.0
    assert out.loc[0, "areal_energy_proxy"] == 0.08
    assert out.loc[0, "pulse_density_proxy"] == 4.0
    assert out.loc[0, "line_energy_proxy"] == 0.2
    assert out.loc[0, "pulse_spacing_um"] == 0.1
    assert out.loc[0, "layer_count_proxy"] == 10.0


def test_cutting_cold_start_recommendation_has_null_predictions(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(
        cfg,
        "SiC",
        "quality_first",
        process_type="cutting",
        parameter_bounds=_cutting_bounds(),
        requirements={"material_thickness_um": 500, "cut_through_required": True, "target_kerf_width_um": 30},
    )
    rec = recommend_parameters(state, "balanced")
    assert rec["process_type"] == "cutting"
    assert rec["model_status"] == "rule_based_cold_start"
    assert all(value is None for value in rec["prediction"].values())
    assert rec["bo_component"]["surrogate_model"] is None


def test_cutting_not_cut_through_feedback_increases_intensity(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", process_type="cutting", parameter_bounds=_cutting_bounds())
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {"iteration": 1, "qualitative_feedback": {"cut_through_level": "未切透", "efficiency_level": "较小"}},
    )
    rec2 = recommend_next(state, "balanced")
    p1 = rec1["recommended_parameters"]
    p2 = rec2["recommended_parameters"]
    assert p2["laser_power_W"] >= p1["laser_power_W"]
    assert p2["scan_speed_mm_s"] <= p1["scan_speed_mm_s"]
    assert p2["passes"] >= p1["passes"]
    assert p2["layer_step_um"] <= p1["layer_step_um"]
    assert rec2["feedback_interpretation"]["suggested_direction"]["conflict"] is False


def test_cutting_overburn_feedback_decreases_intensity(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", process_type="cutting", parameter_bounds=_cutting_bounds())
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {"iteration": 1, "qualitative_feedback": {"cut_through_level": "严重过烧蚀", "kerf_width_level": "很大"}},
    )
    rec2 = recommend_next(state, "balanced")
    p1 = rec1["recommended_parameters"]
    p2 = rec2["recommended_parameters"]
    assert p2["laser_power_W"] <= p1["laser_power_W"]
    assert p2["scan_speed_mm_s"] >= p1["scan_speed_mm_s"]
    assert p2["passes"] <= p1["passes"]
    assert rec2["feedback_interpretation"]["suggested_direction"]["conflict"] is False


def test_milling_backward_compatibility_without_process_type(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "balanced", target_depth_um=20)
    rec = recommend_parameters(state, "balanced")
    assert state["process_type"] == "milling"
    assert rec["process_type"] == "milling"
    assert rec["bo_component"]["surrogate_model"] == "GPR"


def test_legacy_milling_feedback_json_aliases_are_preserved():
    payload = {
        "task_id": "SiC_20260630_001",
        "iteration": 1,
        "qualitative_feedback": {"roughness": "too_large", "depth": "too_shallow", "efficiency": "acceptable"},
    }
    out = validate_feedback(payload, "milling")
    assert out["qualitative_feedback"] == {"roughness": "较大", "depth": "较小", "efficiency": "适中"}


def test_model_status_thresholds():
    assert model_status_from_sample_count(9) == "rule_based_cold_start"
    assert model_status_from_sample_count(10) == "hybrid_rule_bo"
    assert model_status_from_sample_count(29) == "hybrid_rule_bo"
    assert model_status_from_sample_count(30) == "data_driven_bo"
