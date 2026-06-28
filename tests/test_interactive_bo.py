from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from src.acquisition import apply_qualitative_feedback_rules
from src.features import add_engineered_features
from src.interactive_bo import (
    feedback_json,
    init_task,
    load_task_state,
    recommend_next,
    recommend_parameters,
    run_json,
    submit_feedback,
)
from src.ui_app import task_history_table


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
                "material": "SiC",
                "pulse_width_ps": [0.5, 1.0, 2.0][i % 3],
                "frequency_kHz": frequency,
                "hatch_spacing_um": spacing,
                "passes": passes,
                "scan_speed_mm_s": speed,
                "power_W": None,
                "depth_um": 8 + 18 * d_proxy + (i % 3),
                "Sa_um": 0.4 + 2.2 * d_proxy,
                "Sq_um": None,
                "Sz_um": None,
                "source_file": "synthetic",
                "valid_flag": True,
                "note": "",
            }
        )
    df = add_engineered_features(pd.DataFrame(rows))
    df.to_csv(root / "data" / "processed" / "unified_experiments_with_features.csv", index=False)
    shutil.copy(
        root / "data" / "processed" / "unified_experiments_with_features.csv",
        root / "data" / "processed" / "updated_experiments.csv",
    )
    return {"_root": str(root), "output_dir": str(root / "outputs"), "random_seed": 42, "bo_candidate_grid_size": 250, "lambda_sa": 0.25}


def _d_proxy(params: dict) -> float:
    return params["frequency_kHz"] * params["passes"] / (params["scan_speed_mm_s"] * params["hatch_spacing_um"])


def _state_path(cfg: dict, task_id: str) -> Path:
    return Path(cfg["output_dir"]) / "tasks" / f"{task_id}_task_state.json"


def test_init_task_creates_state(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", target_depth_um=20, Sa_max_um=2.0)
    assert state["task_id"].startswith("SiC_")
    assert state["available_historical_samples"] == 18
    assert Path(cfg["output_dir"], "task_state.json").exists()


def test_recommendation_has_required_fields(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "balanced", target_depth_um=20, Sa_max_um=2.0)
    rec = recommend_parameters(state, "balanced")
    assert {"pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s"}.issubset(rec["recommended_parameters"])
    assert "depth_um" in rec["prediction"]
    assert "score" in rec["acquisition"]
    assert rec["bo_component"]["surrogate_model"] == "GPR"
    assert rec["feedback_rule_component"]["applied"] is False


def test_feedback_numeric_updates_history(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "balanced", target_depth_um=20)
    rec = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec["task_id"]))
    updated = submit_feedback(
        state,
        {
            "iteration": 1,
            "measured_result": {"depth_um": 21.0, "Sa_um": 1.1},
            "qualitative_feedback": {"roughness": "acceptable", "depth": "acceptable", "efficiency": "unknown"},
        },
    )
    assert updated["history"][0]["feedback"]["numeric_feedback_used"] is True
    data = pd.read_csv(Path(cfg["data_path"]) if "data_path" in cfg else Path(cfg["output_dir"]).parent / "data" / "processed" / "updated_experiments.csv")
    assert "interactive_feedback" in str(data.iloc[-1]["source_file"])


def test_feedback_qualitative_does_not_create_fake_measurement(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", depth_min_um=15, Sa_max_um=2.0)
    rec = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec["task_id"]))
    before = len(pd.read_csv(Path(cfg["output_dir"]).parent / "data" / "processed" / "updated_experiments.csv"))
    updated = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "too_large", "depth": "acceptable", "efficiency": "unknown"},
        },
    )
    after = len(pd.read_csv(Path(cfg["output_dir"]).parent / "data" / "processed" / "updated_experiments.csv"))
    assert updated["history"][0]["feedback"]["numeric_feedback_used"] is False
    assert before == after
    assert updated["history"][0]["feedback"]["measured_result"]["depth_um"] is None


def test_recommend_next_changes_direction_when_roughness_too_large(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", depth_min_um=12, Sa_max_um=1.5)
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "too_large", "depth": "acceptable", "efficiency": "unknown"},
        },
    )
    rec2 = recommend_next(state, "balanced")
    assert rec2["D_proxy"] <= rec1["D_proxy"] * 1.05


def test_recommend_next_changes_direction_when_depth_too_shallow(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "balanced", target_depth_um=24, Sa_max_um=2.5)
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "acceptable", "depth": "too_shallow", "efficiency": "unknown"},
        },
    )
    rec2 = recommend_next(state, "balanced")
    assert rec2["D_proxy"] >= rec1["D_proxy"] * 0.95


def test_five_level_feedback_strength_direction(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", depth_min_um=12, Sa_max_um=1.5)
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "很大", "depth": "适中", "efficiency": "适中"},
        },
    )
    assert state["history"][0]["feedback"]["qualitative_feedback"]["roughness"] == "很大"
    rec2 = recommend_next(state, "balanced")
    assert rec2["D_proxy"] <= rec1["D_proxy"]
    assert rec2["feedback_interpretation"]["roughness_score"] == 2
    assert rec2["feedback_rule_component"]["applied"] is True
    assert "raw_acquisition_score" in rec2["bo_component"]


def test_stronger_roughness_feedback_has_larger_penalty():
    scored = pd.DataFrame(
        {
            "D_proxy": [0.5, 1.0, 2.0],
            "scan_speed_mm_s": [100.0, 80.0, 50.0],
            "hatch_spacing_um": [8.0, 6.0, 4.0],
            "passes": [1.0, 2.0, 4.0],
            "predicted_depth_um": [10.0, 12.0, 14.0],
            "predicted_Sa_um": [0.8, 1.2, 2.0],
            "acquisition_score": [0.0, 0.0, 0.0],
        }
    )
    weak, _, weak_meta = apply_qualitative_feedback_rules(scored, {"roughness": "较大"}, {"frequency_kHz": 10, "passes": 2, "scan_speed_mm_s": 10, "hatch_spacing_um": 2})
    strong, _, strong_meta = apply_qualitative_feedback_rules(scored, {"roughness": "很大"}, {"frequency_kHz": 10, "passes": 2, "scan_speed_mm_s": 10, "hatch_spacing_um": 2})
    assert weak_meta["feedback_rule_component"]["rule_strength"] == 1
    assert strong_meta["feedback_rule_component"]["rule_strength"] == 2
    assert abs(strong.loc[2, "rule_adjustment"]) > abs(weak.loc[2, "rule_adjustment"])


def test_stronger_efficiency_feedback_has_larger_d_proxy_bias():
    scored = pd.DataFrame(
        {
            "D_proxy": [0.5, 1.0, 2.0],
            "scan_speed_mm_s": [50.0, 80.0, 100.0],
            "hatch_spacing_um": [8.0, 6.0, 4.0],
            "passes": [1.0, 2.0, 4.0],
            "predicted_depth_um": [10.0, 12.0, 14.0],
            "predicted_Sa_um": [0.8, 1.2, 2.0],
            "acquisition_score": [0.0, 0.0, 0.0],
        }
    )
    weak, _, _ = apply_qualitative_feedback_rules(scored, {"efficiency": "较小"}, {"frequency_kHz": 10, "passes": 2, "scan_speed_mm_s": 10, "hatch_spacing_um": 2})
    strong, _, _ = apply_qualitative_feedback_rules(scored, {"efficiency": "很小"}, {"frequency_kHz": 10, "passes": 2, "scan_speed_mm_s": 10, "hatch_spacing_um": 2})
    assert strong.loc[2, "rule_adjustment"] > weak.loc[2, "rule_adjustment"]


def test_conflict_feedback_records_resolution(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "balanced", target_depth_um=20, Sa_max_um=2.0)
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "很大", "depth": "适中", "efficiency": "很小"},
        },
    )
    rec2 = recommend_next(state, "balanced")
    direction = rec2["feedback_interpretation"]["suggested_direction"]
    assert direction["conflict"] is True
    assert direction["resolution"] == "balanced_tradeoff"
    assert rec2["feedback_rule_component"]["decrease_strength"] == 2
    assert rec2["feedback_rule_component"]["increase_strength"] == 2


def test_quality_first_conflict_prioritizes_roughness_direction(tmp_path):
    cfg = _config(tmp_path)
    state = init_task(cfg, "SiC", "quality_first", depth_min_um=12, Sa_max_um=1.5)
    rec1 = recommend_parameters(state, "balanced")
    state = load_task_state(_state_path(cfg, rec1["task_id"]))
    state = submit_feedback(
        state,
        {
            "iteration": 1,
            "qualitative_feedback": {"roughness": "很大", "depth": "适中", "efficiency": "很小"},
        },
    )
    rec2 = recommend_next(state, "balanced")
    assert rec2["feedback_interpretation"]["suggested_direction"]["conflict"] is True
    assert rec2["feedback_interpretation"]["suggested_direction"]["resolution"].startswith("quality_first")
    assert rec2["D_proxy"] < rec1["D_proxy"]


def test_ui_imports_without_running_streamlit():
    assert callable(task_history_table)


def test_json_interface_roundtrip(tmp_path):
    cfg = _config(tmp_path)
    request_path = tmp_path / "task_request.json"
    request_path.write_text(
        json.dumps(
            {
                "material": "SiC",
                "objective_mode": "quality_first",
                "target_depth_um": 20,
                "Sa_max_um": 2.0,
                "recommendation_type": "balanced",
            }
        ),
        encoding="utf-8",
    )
    rec1 = run_json(request_path, cfg)
    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "task_id": rec1["task_id"],
                "iteration": rec1["iteration"],
                "measured_result": {"depth_um": 18.0, "Sa_um": 2.2},
                "qualitative_feedback": {"roughness": "too_large", "depth": "acceptable", "efficiency": "unknown"},
            }
        ),
        encoding="utf-8",
    )
    rec2 = feedback_json(feedback_path)
    assert rec2["task_id"] == rec1["task_id"]
    assert rec2["iteration"] == 2
