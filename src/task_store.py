"""Persistent task storage for the interactive BO demo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def utc_timestamp() -> str:
    """Return an ISO-like UTC timestamp without relying on local formatting."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_task_id(material: str, output_dir: str | Path = "outputs") -> str:
    """Generate a stable readable task id using material, date and sequence."""
    date = datetime.now(UTC).strftime("%Y%m%d")
    safe_material = "".join(ch if ch.isalnum() else "_" for ch in str(material))
    tasks_dir = Path(output_dir) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(tasks_dir.glob(f"{safe_material}_{date}_*_task_state.json"))
    return f"{safe_material}_{date}_{len(existing) + 1:03d}"


def task_state_path(task_id: str, output_dir: str | Path = "outputs") -> Path:
    """Return the canonical task-state path for a task id."""
    return Path(output_dir) / "tasks" / f"{task_id}_task_state.json"


def save_task_state(task_state: dict[str, Any], path: str | Path | None = None) -> None:
    """Persist a task state and update the latest task_state.json snapshot."""
    output_dir = Path(task_state.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tasks").mkdir(parents=True, exist_ok=True)
    target = Path(path) if path is not None else task_state_path(task_state["task_id"], output_dir)
    target.write_text(json.dumps(task_state, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "task_state.json").write_text(json.dumps(task_state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_task_state(task_id_or_path: str | Path, output_dir: str | Path = "outputs") -> dict[str, Any]:
    """Load a task by explicit path or task id."""
    candidate = Path(task_id_or_path)
    if not candidate.exists():
        candidate = task_state_path(str(task_id_or_path), output_dir)
    if not candidate.exists():
        raise FileNotFoundError(f"Task state not found: {task_id_or_path}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def write_latest_recommendation(recommendation: dict[str, Any], output_dir: str | Path = "outputs") -> Path:
    """Write outputs/recommendation.json."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "recommendation.json"
    path.write_text(json.dumps(recommendation, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_recommendation_log(task_state: dict[str, Any], recommendation: dict[str, Any]) -> Path:
    """Append one recommendation to outputs/recommendation_log.csv."""
    output_dir = Path(task_state.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    row = _flatten_recommendation(recommendation)
    return _append_csv(output_dir / "recommendation_log.csv", row)


def append_feedback_log(task_state: dict[str, Any], feedback_record: dict[str, Any]) -> Path:
    """Append one feedback record to outputs/feedback_log.csv."""
    output_dir = Path(task_state.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "task_id": task_state["task_id"],
        "process_type": task_state.get("process_type", "milling"),
        "iteration": feedback_record.get("iteration"),
        "measured_depth_um": feedback_record.get("measured_result", {}).get("depth_um"),
        "measured_Sa_um": feedback_record.get("measured_result", {}).get("Sa_um"),
        "processing_time_s": feedback_record.get("measured_result", {}).get("processing_time_s"),
        "roughness_feedback": feedback_record.get("qualitative_feedback", {}).get("roughness"),
        "depth_feedback": feedback_record.get("qualitative_feedback", {}).get("depth"),
        "efficiency_feedback": feedback_record.get("qualitative_feedback", {}).get("efficiency"),
        "cut_through_level": feedback_record.get("qualitative_feedback", {}).get("cut_through_level"),
        "kerf_width_level": feedback_record.get("qualitative_feedback", {}).get("kerf_width_level"),
        "edge_roughness_level": feedback_record.get("qualitative_feedback", {}).get("edge_roughness_level"),
        "taper_level": feedback_record.get("qualitative_feedback", {}).get("taper_level"),
        "chipping_level": feedback_record.get("qualitative_feedback", {}).get("chipping_level"),
        "numeric_feedback_used": feedback_record.get("numeric_feedback_used", False),
        "qualitative_rules_used": feedback_record.get("qualitative_rules_used", False),
        "note": feedback_record.get("note", ""),
        "created_at": feedback_record.get("created_at"),
    }
    return _append_csv(output_dir / "feedback_log.csv", row)


def export_task_logs(task_state: dict[str, Any], output_dir: str | Path = "outputs") -> dict[str, str]:
    """Export per-task recommendation, feedback and state files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    task_id = task_state["task_id"]
    recommendations = [_flatten_recommendation(item["recommendation"]) for item in task_state.get("history", []) if "recommendation" in item]
    feedback = []
    for item in task_state.get("history", []):
        if "feedback" in item:
            record = item["feedback"]
            feedback.append(
                {
                    "task_id": task_id,
                    "iteration": item.get("iteration"),
                    "measured_depth_um": record.get("measured_result", {}).get("depth_um"),
                    "measured_Sa_um": record.get("measured_result", {}).get("Sa_um"),
                    "processing_time_s": record.get("measured_result", {}).get("processing_time_s"),
                    "roughness_feedback": record.get("qualitative_feedback", {}).get("roughness"),
                    "depth_feedback": record.get("qualitative_feedback", {}).get("depth"),
                    "efficiency_feedback": record.get("qualitative_feedback", {}).get("efficiency"),
                    "cut_through_level": record.get("qualitative_feedback", {}).get("cut_through_level"),
                    "kerf_width_level": record.get("qualitative_feedback", {}).get("kerf_width_level"),
                    "edge_roughness_level": record.get("qualitative_feedback", {}).get("edge_roughness_level"),
                    "taper_level": record.get("qualitative_feedback", {}).get("taper_level"),
                    "chipping_level": record.get("qualitative_feedback", {}).get("chipping_level"),
                    "numeric_feedback_used": record.get("numeric_feedback_used", False),
                    "qualitative_rules_used": record.get("qualitative_rules_used", False),
                    "note": record.get("note", ""),
                    "created_at": record.get("created_at"),
                }
            )
    rec_path = out / f"{task_id}_recommendation_log.csv"
    fb_path = out / f"{task_id}_feedback_log.csv"
    state_path = out / f"{task_id}_task_state.json"
    pd.DataFrame(recommendations).to_csv(rec_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(feedback).to_csv(fb_path, index=False, encoding="utf-8-sig")
    state_path.write_text(json.dumps(task_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"recommendation_log": str(rec_path), "feedback_log": str(fb_path), "task_state": str(state_path)}


def _append_csv(path: Path, row: dict[str, Any]) -> Path:
    """Append one row to a CSV file."""
    df = pd.DataFrame([row])
    header = not path.exists()
    df.to_csv(path, mode="a", header=header, index=False, encoding="utf-8-sig")
    return path


def _flatten_recommendation(recommendation: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested recommendation JSON for CSV logs."""
    params = recommendation.get("recommended_parameters", {})
    pred = recommendation.get("prediction", {})
    acq = recommendation.get("acquisition", {})
    bo = recommendation.get("bo_component", {})
    rule = recommendation.get("feedback_rule_component", {})
    interpretation = recommendation.get("feedback_interpretation", {})
    direction = interpretation.get("suggested_direction", {})
    penalty = rule.get("penalty_or_bias", {})
    return {
        "task_id": recommendation.get("task_id"),
        "process_type": recommendation.get("process_type", "milling"),
        "iteration": recommendation.get("iteration"),
        "material": recommendation.get("material"),
        "model_status": recommendation.get("model_status"),
        "objective_mode": recommendation.get("objective_mode"),
        "pulse_width_ps": params.get("pulse_width_ps"),
        "frequency_kHz": params.get("frequency_kHz"),
        "hatch_spacing_um": params.get("hatch_spacing_um"),
        "passes": params.get("passes"),
        "scan_speed_mm_s": params.get("scan_speed_mm_s"),
        "power_W": params.get("power_W"),
        "laser_power_W": params.get("laser_power_W"),
        "focus_offset_um": params.get("focus_offset_um"),
        "layer_step_um": params.get("layer_step_um"),
        "fill_pattern": params.get("fill_pattern"),
        "predicted_depth_um": pred.get("depth_um"),
        "predicted_depth_std_um": pred.get("depth_std_um"),
        "predicted_Sa_um": pred.get("Sa_um"),
        "predicted_Sa_std_um": pred.get("Sa_std_um"),
        "cut_through_probability": pred.get("cut_through_probability"),
        "kerf_top_width_um": pred.get("kerf_top_width_um"),
        "kerf_bottom_width_um": pred.get("kerf_bottom_width_um"),
        "kerf_taper_deg": pred.get("kerf_taper_deg"),
        "cut_edge_Sa_um": pred.get("cut_edge_Sa_um"),
        "HAZ_width_um": pred.get("HAZ_width_um"),
        "chipping_um": pred.get("chipping_um"),
        "acquisition_type": acq.get("type"),
        "acquisition_score": acq.get("score"),
        "bo_raw_acquisition_score": bo.get("raw_acquisition_score"),
        "rule_adjustment": penalty.get("selected_rule_adjustment"),
        "feedback_rule_applied": rule.get("applied"),
        "feedback_rule_strength": rule.get("rule_strength"),
        "feedback_conflict": direction.get("conflict"),
        "feedback_resolution": direction.get("resolution"),
        "roughness_model_available": recommendation.get("roughness_model_available"),
        "within_observed_range": recommendation.get("within_observed_range"),
        "reason": recommendation.get("reason"),
        "final_selection_reason": recommendation.get("final_selection_reason"),
        "created_at": recommendation.get("created_at"),
    }
