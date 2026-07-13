"""Interactive Bayesian optimization workflow for process recommendations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .acquisition import apply_qualitative_feedback_rules
from .features import add_engineered_features
from .interface import validate_feedback, validate_task_request
from .objectives import valid_sample_count
from .recommendation_rules import apply_cutting_feedback_to_parameters, cold_start_cutting_parameters, cutting_prediction_nulls
from .schema import normalize_feedback_level, normalize_fill_pattern, normalize_process_type, model_status_from_sample_count
from .task_store import (
    append_feedback_log,
    append_recommendation_log,
    export_task_logs as store_export_task_logs,
    generate_task_id,
    load_task_state as store_load_task_state,
    save_task_state as store_save_task_state,
    utc_timestamp,
    write_latest_recommendation,
)


PROCESS_COLUMNS = ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s"]
CUTTING_PROCESS_COLUMNS = ["pulse_width_ps", "frequency_kHz", "laser_power_W", "scan_speed_mm_s", "passes", "focus_offset_um", "layer_step_um", "hatch_spacing_um", "fill_pattern"]
OBJECTIVE_MODES = {"quality_first", "efficiency_first", "balanced"}
RECOMMENDATION_TYPES = {"exploitation", "exploration", "balanced"}
QUALITATIVE_DEFAULTS = {"roughness": "unknown", "depth": "unknown", "efficiency": "unknown"}
LEVEL_VALUES = {"很小", "较小", "适中", "较大", "很大", "unknown"}
LEGACY_QUALITATIVE_MAP = {
    "roughness": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "depth": {"acceptable": "适中", "too_shallow": "较小", "too_deep": "较大", "unknown": "unknown"},
    "efficiency": {"acceptable": "适中", "too_low": "较小", "too_high": "较大", "unknown": "unknown"},
}


def init_task(
    config: dict[str, Any],
    material: str,
    objective_mode: str,
    process_type: str = "milling",
    target_depth_um: float | None = None,
    depth_min_um: float | None = None,
    Sa_max_um: float | None = None,
    parameter_bounds: dict[str, list[float]] | None = None,
    requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Initialize an interactive recommendation task and persist its state."""
    if objective_mode not in OBJECTIVE_MODES:
        raise ValueError(f"Unsupported objective_mode: {objective_mode}")
    process_type = normalize_process_type(process_type)
    data = load_experiment_data(config)
    known_material = material in set(data["material"].dropna().astype(str))
    allow_unknown_cutting = process_type == "cutting" and bool(parameter_bounds)
    if not known_material and not allow_unknown_cutting:
        available = sorted(data["material"].dropna().astype(str).unique())
        raise ValueError(f"Material {material!r} not found. Available materials: {available}")

    material_data = data.iloc[0:0].copy() if not known_material else _material_data(data, material, process_type)
    bounds = resolve_parameter_bounds(material_data, parameter_bounds, process_type)
    output_path = _output_dir(config)
    output_value = _posix_path_string(config.get("output_dir", "outputs"))
    if Path(output_value).is_absolute():
        data_value = _posix_path_string(_data_path(config))
    else:
        data_value = _posix_path_string(config.get("data_path", "data/processed/updated_experiments.csv"))
    task_id_prefix = material if process_type == "milling" else f"{process_type}_{material}"
    task_id = generate_task_id(task_id_prefix, output_path)
    depth_available = _model_available(material_data, "depth_um")
    sa_available = _model_available(material_data, "Sa_um")
    n_valid = valid_sample_count(data, process_type, material)
    model_status = model_status_from_sample_count(n_valid)
    if process_type == "cutting" and n_valid < 10:
        model_status = "rule_based_cold_start"
    warnings = []
    if not known_material:
        warnings.append("No historical material data found; cutting task uses rule-based cold-start bounds only.")
    if process_type == "milling" and objective_mode == "quality_first" and not sa_available:
        warnings.append("Sa model unavailable; quality_first will fall back to conservative depth/D_proxy recommendations.")
    if process_type == "milling" and objective_mode == "balanced" and not sa_available:
        warnings.append("Sa model unavailable; balanced mode will use depth target only.")

    now = utc_timestamp()
    task_state = {
        "task_id": task_id,
        "created_at": now,
        "updated_at": now,
        "material": material,
        "process_type": process_type,
        "objective_mode": objective_mode,
        "requirements": requirements or {},
        "target_depth_um": _none_or_float(target_depth_um),
        "depth_min_um": _none_or_float(depth_min_um),
        "Sa_max_um": _none_or_float(Sa_max_um),
        "parameter_bounds": bounds,
        "available_historical_samples": int(len(material_data)),
        "n_valid_process_material_samples": int(n_valid),
        "model_status": model_status,
        "depth_model_available": depth_available,
        "roughness_model_available": sa_available,
        "output_dir": output_value,
        "data_path": data_value,
        "lambda_sa": float(config.get("lambda_sa", 0.25)),
        "bo_candidate_grid_size": int(config.get("bo_candidate_grid_size", 3000)),
        "random_seed": int(config.get("random_seed", 42)),
        "history": [],
        "warnings": warnings,
    }
    save_task_state(task_state)
    return task_state


def recommend_parameters(task_state: dict[str, Any], recommendation_type: str = "balanced") -> dict[str, Any]:
    """Recommend one process parameter set for the current task state."""
    if recommendation_type not in RECOMMENDATION_TYPES:
        raise ValueError(f"Unsupported recommendation_type: {recommendation_type}")
    if task_state.get("process_type", "milling") == "cutting" and task_state.get("model_status") == "rule_based_cold_start":
        return recommend_cutting_cold_start(task_state, recommendation_type)
    from ultrafast_bo.application import BORecommendationService

    data = load_experiment_data(task_state)
    material = task_state["material"]
    material_data = _material_data(data, material, task_state.get("process_type", "milling"))
    samples = []
    for index, row in material_data.iterrows():
        parameters = {
            name: float(row[name])
            for name in PROCESS_COLUMNS
            if name in row and pd.notna(row[name])
        }
        metrics = {
            name: float(row[name])
            for name in ("depth_um", "Sa_um")
            if name in row and pd.notna(row[name])
        }
        samples.append(
            {
                "sample_id": str(row.get("record_id") or f"legacy-{index}"),
                "material": material,
                "process_type": task_state.get("process_type", "milling"),
                "x_parameters": parameters,
                "y_metrics": metrics,
                "valid_for_training": bool(row.get("valid_flag", False)),
                "feature_schema_version": "1.0",
                "run_status": "completed",
            }
        )
    formal = BORecommendationService().recommend(
        {
            "material": material,
            "process_type": task_state.get("process_type", "milling"),
            "objective_metric": "depth_um",
            "feature_schema_version": "1.0",
            "objective_version": "legacy-depth-v1",
            "acquisition_version": f"legacy-{recommendation_type}-adapter-v1",
            "random_seed": int(task_state.get("random_seed", 42)),
        },
        samples,
        {
            "active": True,
            "machine_bounds": task_state.get("parameter_bounds") or {},
            "revision_id": "legacy-task-bounds-v1",
        },
    )
    if formal.get("status") == "blocked" or not formal.get("recommended_parameters"):
        raise ValueError("Formal BO service could not produce a governed recommendation: " + "; ".join(formal.get("blocking_reasons") or []))
    params = dict(formal["recommended_parameters"])
    for name in PROCESS_COLUMNS:
        if name not in params and name in task_state.get("parameter_bounds", {}):
            lower, upper = task_state["parameter_bounds"][name]
            params[name] = lower + 0.35 * (upper - lower)
    d_proxy = _d_proxy_from_parameters(params)
    feedback_rule_reason = "No prior feedback rule applied."
    feedback_metadata = {
        "feedback_interpretation": {},
        "feedback_rule_component": {"applied": False, "rule_strength": 0, "penalty_or_bias": {}},
    }
    last_feedback = _last_feedback(task_state)
    if last_feedback:
        previous_params = _last_recommendation(task_state).get("recommended_parameters", {}) if _last_recommendation(task_state) else {}
        probe = pd.DataFrame([{**params, "D_proxy": d_proxy, "predicted_depth_um": (formal.get("predictions") or {}).get("mean"), "predicted_Sa_um": np.nan, "acquisition_score": (formal.get("acquisition") or {}).get("score") or 0.0}])
        _, feedback_rule_reason, feedback_metadata = apply_qualitative_feedback_rules(
            probe,
            last_feedback.get("qualitative_feedback"),
            previous_params,
            task_state["objective_mode"],
        )
        params = _apply_feedback_direction(params, previous_params, feedback_metadata, task_state)
        d_proxy = _d_proxy_from_parameters(params)
    iteration = len(task_state.get("history", [])) + 1
    prediction = formal.get("predictions") or {}
    recommendation = {
        "task_id": task_state["task_id"], "iteration": iteration,
        "process_type": task_state.get("process_type", "milling"), "material": material,
        "model_status": formal.get("engine_model_status") or formal.get("model_status"),
        "objective_mode": task_state["objective_mode"], "recommended_parameters": params,
        "prediction": {"depth_um": prediction.get("mean"), "depth_std_um": prediction.get("uncertainty"), "Sa_um": None, "Sa_std_um": None},
        "acquisition": formal.get("acquisition") or {"type": recommendation_type, "score": None},
        "bo_component": {
            "surrogate_model": "GPR" if formal.get("bo_invoked") else None,
            "acquisition": recommendation_type, "raw_acquisition_score": (formal.get("acquisition") or {}).get("score"),
            "predicted_mean": {"depth_um": prediction.get("mean"), "Sa_um": None},
            "predicted_std": {"depth_um": prediction.get("uncertainty"), "Sa_um": None},
            "bo_run_id": formal.get("bo_run_id"), "model_version": formal.get("model_version"),
            "dataset_version": formal.get("dataset_version"),
        },
        "feedback_interpretation": feedback_metadata.get("feedback_interpretation", {}),
        "feedback_rule_component": feedback_metadata.get("feedback_rule_component", {}),
        "final_selection_reason": feedback_rule_reason,
        "roughness_model_available": False, "within_observed_range": True,
        "D_proxy": d_proxy,
        "reason": "Candidate produced by the governed BO service and legacy response adapter.",
        "created_at": utc_timestamp(),
    }

    task_state.setdefault("history", []).append(
        {
            "iteration": iteration,
            "recommendation": recommendation,
            "feedback": {},
            "numeric_feedback_used": False,
            "qualitative_rules_used": last_feedback is not None,
            "next_recommendation_reason": recommendation["reason"],
            "created_at": recommendation["created_at"],
        }
    )
    task_state["updated_at"] = utc_timestamp()
    save_task_state(task_state)
    write_latest_recommendation(recommendation, task_state.get("output_dir", "outputs"))
    append_recommendation_log(task_state, recommendation)
    return recommendation


def submit_feedback(task_state: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    """Submit numeric or qualitative feedback for a previous recommendation."""
    iteration = int(feedback.get("iteration") or _latest_iteration(task_state))
    history_item = _history_item(task_state, iteration)
    if history_item is None:
        raise ValueError(f"Iteration {iteration} not found in task {task_state['task_id']}")
    measured = _normalize_measured_result(feedback.get("measured_result", {}), feedback, task_state.get("process_type", "milling"))
    qualitative = _normalize_qualitative_feedback(feedback.get("qualitative_feedback", {}), feedback, task_state.get("process_type", "milling"))
    numeric_used = any(measured.get(key) is not None for key in ["depth_um", "Sa_um"])
    qualitative_used = any(value != "unknown" for value in qualitative.values())
    record = {
        "iteration": iteration,
        "measured_result": measured,
        "qualitative_feedback": qualitative,
        "note": feedback.get("note", ""),
        "numeric_feedback_used": numeric_used,
        "qualitative_rules_used": qualitative_used,
        "created_at": utc_timestamp(),
    }
    history_item["feedback"] = record
    history_item["numeric_feedback_used"] = numeric_used
    history_item["qualitative_rules_used"] = qualitative_used
    if numeric_used:
        append_numeric_feedback_to_data(task_state, history_item["recommendation"], measured, record.get("note", ""))
    task_state["updated_at"] = utc_timestamp()
    save_task_state(task_state)
    append_feedback_log(task_state, record)
    return task_state


def recommend_next(task_state: dict[str, Any], recommendation_type: str = "balanced") -> dict[str, Any]:
    """Recommend the next process parameter set after feedback has been stored."""
    return recommend_parameters(task_state, recommendation_type)


def recommend_cutting_cold_start(task_state: dict[str, Any], recommendation_type: str = "balanced") -> dict[str, Any]:
    """Recommend cutting parameters using cold-start rules with null predictions."""
    previous = _last_recommendation(task_state)
    last_feedback = _last_feedback(task_state)
    if previous and last_feedback:
        params, interpretation, rule_reason = apply_cutting_feedback_to_parameters(
            previous.get("recommended_parameters", {}),
            last_feedback.get("qualitative_feedback", {}),
            task_state.get("parameter_bounds", {}),
            task_state.get("objective_mode", "balanced"),
        )
        rule_applied = True
        reason = rule_reason
    else:
        params = cold_start_cutting_parameters(task_state.get("parameter_bounds", {}), task_state.get("requirements", {}))
        interpretation = {
            "suggested_direction": {
                "cutting_intensity": "cold_start_conservative",
                "conflict": False,
                "resolution": "no_feedback_initial_recommendation",
                "raw_reasons": [],
            }
        }
        rule_applied = False
        reason = "No valid cutting data available. Recommendation generated by conservative cold-start rules within user-defined bounds."
    iteration = len(task_state.get("history", [])) + 1
    recommendation = {
        "task_id": task_state["task_id"],
        "iteration": iteration,
        "process_type": "cutting",
        "material": task_state["material"],
        "objective_mode": task_state["objective_mode"],
        "model_status": "rule_based_cold_start",
        "recommended_parameters": params,
        "prediction": cutting_prediction_nulls(),
        "acquisition": {"type": recommendation_type, "score": None},
        "bo_component": {
            "surrogate_model": None,
            "acquisition": None,
            "predicted_mean": {},
            "predicted_std": {},
            "note": "No cutting surrogate is trained because there are not enough valid cutting samples.",
        },
        "feedback_interpretation": interpretation,
        "feedback_rule_component": {"applied": rule_applied, "rule_strength": max(interpretation.get("increase_energy_strength", 0), interpretation.get("decrease_energy_strength", 0)), "penalty_or_bias": {}},
        "final_selection_reason": "Rule-based cold-start candidate selected; BO will be enabled after enough cutting data are available.",
        "roughness_model_available": False,
        "within_observed_range": True,
        "reason": reason,
        "created_at": utc_timestamp(),
    }
    task_state.setdefault("history", []).append(
        {
            "iteration": iteration,
            "recommendation": recommendation,
            "feedback": {},
            "numeric_feedback_used": False,
            "qualitative_rules_used": rule_applied,
            "next_recommendation_reason": recommendation["reason"],
            "created_at": recommendation["created_at"],
        }
    )
    task_state["updated_at"] = utc_timestamp()
    save_task_state(task_state)
    write_latest_recommendation(recommendation, task_state.get("output_dir", "outputs"))
    append_recommendation_log(task_state, recommendation)
    return recommendation


def save_task_state(task_state: dict[str, Any], path: str | Path | None = None) -> None:
    """Save a task state to disk."""
    store_save_task_state(task_state, path)


def load_task_state(task_id_or_path: str | Path) -> dict[str, Any]:
    """Load a task state from id or path."""
    return store_load_task_state(task_id_or_path)


def export_task_logs(task_state: dict[str, Any], output_dir: str | Path = "outputs") -> dict[str, str]:
    """Export current task logs to task-specific files."""
    return store_export_task_logs(task_state, output_dir)


def run_json(task_request_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    """Initialize a task from JSON and write the first recommendation."""
    request = validate_task_request(json.loads(Path(task_request_path).read_text(encoding="utf-8")))
    for required in ["material", "objective_mode"]:
        if required not in request:
            raise ValueError(f"Missing required task_request field: {required}")
    state = init_task(
        config,
        material=request["material"],
        objective_mode=request["objective_mode"],
        process_type=request.get("process_type", "milling"),
        target_depth_um=request.get("target_depth_um"),
        depth_min_um=request.get("depth_min_um"),
        Sa_max_um=request.get("Sa_max_um"),
        parameter_bounds=request.get("parameter_bounds"),
        requirements=request.get("requirements"),
    )
    return recommend_parameters(state, request.get("recommendation_type", "balanced"))


def feedback_json(feedback_path: str | Path) -> dict[str, Any]:
    """Load feedback JSON, update the task and write the next recommendation."""
    path = Path(feedback_path)
    feedback = json.loads(path.read_text(encoding="utf-8"))
    if "task_id" not in feedback:
        raise ValueError("Missing required feedback field: task_id")
    try:
        state = store_load_task_state(feedback["task_id"], path.parent / "outputs")
    except FileNotFoundError:
        state = load_task_state(feedback["task_id"])
    feedback = validate_feedback(feedback, state.get("process_type", "milling"))
    updated = submit_feedback(state, feedback)
    return recommend_next(updated, feedback.get("recommendation_type", "balanced"))


def load_experiment_data(config_or_state: dict[str, Any]) -> pd.DataFrame:
    """Load updated or processed experiment data with engineered features."""
    path = _data_path(config_or_state)
    if not path.exists():
        fallback = _project_root(config_or_state) / "data" / "processed" / "unified_experiments.csv"
        if not fallback.exists():
            raise FileNotFoundError(f"Experiment data not found: {path}")
        data = pd.read_csv(fallback)
    else:
        data = pd.read_csv(path)
    if "process_type" not in data.columns:
        data["process_type"] = "milling"
    else:
        data["process_type"] = data["process_type"].fillna("milling")
    if "laser_power_W" not in data.columns and "power_W" in data.columns:
        data["laser_power_W"] = data["power_W"]
    for col in ["fill_pattern", "focus_offset_um", "layer_step_um", "material_thickness_um", "cut_length_mm"]:
        if col not in data.columns:
            data[col] = np.nan
    return add_engineered_features(data)


def resolve_parameter_bounds(material_data: pd.DataFrame, requested: dict[str, list[float]] | None, process_type: str = "milling") -> dict[str, Any]:
    """Intersect user-specified parameter bounds with historical observed ranges."""
    if process_type == "cutting":
        defaults: dict[str, Any] = {
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
        merged = defaults | (requested or {})
        if "fill_pattern" in merged:
            merged["fill_pattern"] = [normalize_fill_pattern(item) for item in merged["fill_pattern"]]
        return merged
    bounds: dict[str, Any] = {}
    for col in PROCESS_COLUMNS:
        values = pd.to_numeric(material_data[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            raise ValueError(f"No historical values available for parameter {col}")
        hist_low, hist_high = float(values.min()), float(values.max())
        low, high = hist_low, hist_high
        if requested and col in requested and requested[col] is not None:
            if len(requested[col]) != 2:
                raise ValueError(f"parameter_bounds.{col} must contain [min, max]")
            req_low, req_high = float(requested[col][0]), float(requested[col][1])
            low, high = max(hist_low, req_low), min(hist_high, req_high)
        if not np.isfinite(low) or not np.isfinite(high) or low > high:
            raise ValueError(f"Parameter bound intersection is empty for {col}")
        bounds[col] = [low, high]
    if requested:
        for optional in ["laser_power_W", "focus_offset_um", "layer_step_um", "fill_pattern"]:
            if optional in requested:
                bounds[optional] = requested[optional]
    return bounds


def append_numeric_feedback_to_data(
    task_state: dict[str, Any],
    recommendation: dict[str, Any],
    measured: dict[str, Any],
    note: str = "",
) -> Path:
    """Append numeric feedback as a new observed row without inventing missing labels."""
    path = _data_path(task_state)
    data = load_experiment_data(task_state)
    params = recommendation.get("recommended_parameters", {})
    row = {
        "record_id": f"interactive_feedback:{task_state['task_id']}:{recommendation.get('iteration')}",
        "process_type": task_state.get("process_type", "milling"),
        "material": task_state["material"],
        "pulse_width_ps": params.get("pulse_width_ps"),
        "frequency_kHz": params.get("frequency_kHz"),
        "laser_power_W": params.get("laser_power_W", params.get("power_W")),
        "hatch_spacing_um": params.get("hatch_spacing_um"),
        "passes": params.get("passes"),
        "scan_speed_mm_s": params.get("scan_speed_mm_s"),
        "power_W": params.get("power_W"),
        "focus_offset_um": params.get("focus_offset_um"),
        "fill_pattern": params.get("fill_pattern"),
        "layer_step_um": params.get("layer_step_um"),
        "path_overlap_um": np.nan,
        "material_thickness_um": task_state.get("requirements", {}).get("material_thickness_um"),
        "cut_length_mm": task_state.get("requirements", {}).get("cut_length_mm"),
        "depth_um": measured.get("depth_um"),
        "Sa_um": measured.get("Sa_um"),
        "Sq_um": np.nan,
        "Sz_um": np.nan,
        "removal_rate_um3_s": np.nan,
        "cut_through": np.nan,
        "kerf_top_width_um": np.nan,
        "kerf_bottom_width_um": np.nan,
        "kerf_taper_deg": np.nan,
        "cut_edge_Sa_um": np.nan,
        "HAZ_width_um": np.nan,
        "chipping_um": np.nan,
        "objective_mode": task_state.get("objective_mode"),
        "source_file": f"interactive_feedback:{task_state['task_id']}",
        "valid_flag": False,
        "eligibility_status": "candidate_pending_validation_and_approval",
        "note": (note + " | feedback candidate; not approved for BO training").strip(" |"),
    }
    raw_cols = list(dict.fromkeys(list(data.columns) + list(row.keys())))
    base = data.reindex(columns=raw_cols)
    updated = pd.concat([base, pd.DataFrame([row]).reindex(columns=raw_cols)], ignore_index=True)
    updated = add_engineered_features(updated)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _d_proxy_from_parameters(parameters: dict[str, Any]) -> float:
    denominator = float(parameters["scan_speed_mm_s"]) * float(parameters["hatch_spacing_um"])
    return float(parameters["frequency_kHz"]) * float(parameters["passes"]) / denominator


def _apply_feedback_direction(
    parameters: dict[str, Any],
    previous: dict[str, Any],
    metadata: dict[str, Any],
    task_state: dict[str, Any],
) -> dict[str, Any]:
    result = dict(parameters)
    component = metadata.get("feedback_rule_component") or {}
    decrease = int(component.get("decrease_strength") or 0)
    increase = int(component.get("increase_strength") or 0)
    if not previous or (decrease == increase and decrease > 0 and task_state.get("objective_mode") == "balanced"):
        return result
    frequency_bounds = (task_state.get("parameter_bounds") or {}).get("frequency_kHz")
    if not frequency_bounds:
        return result
    if decrease > increase or (decrease == increase and decrease > 0 and task_state.get("objective_mode") == "quality_first"):
        result["frequency_kHz"] = float(frequency_bounds[0])
    elif increase > decrease or (decrease == increase and increase > 0 and task_state.get("objective_mode") == "efficiency_first"):
        result["frequency_kHz"] = float(frequency_bounds[1])
    return result


def _normalize_measured_result(measured: dict[str, Any], raw: dict[str, Any], process_type: str = "milling") -> dict[str, Any]:
    """Normalize numeric feedback fields."""
    if process_type == "cutting":
        return {
            "cut_through": measured.get("cut_through", raw.get("cut_through")),
            "kerf_top_width_um": _none_or_float(measured.get("kerf_top_width_um", raw.get("kerf_top_width_um"))),
            "kerf_bottom_width_um": _none_or_float(measured.get("kerf_bottom_width_um", raw.get("kerf_bottom_width_um"))),
            "kerf_taper_deg": _none_or_float(measured.get("kerf_taper_deg", raw.get("kerf_taper_deg"))),
            "cut_edge_Sa_um": _none_or_float(measured.get("cut_edge_Sa_um", raw.get("cut_edge_Sa_um"))),
            "HAZ_width_um": _none_or_float(measured.get("HAZ_width_um", raw.get("HAZ_width_um"))),
            "chipping_um": _none_or_float(measured.get("chipping_um", raw.get("chipping_um"))),
        }
    return {
        "depth_um": _none_or_float(measured.get("depth_um", raw.get("depth"))),
        "Sa_um": _none_or_float(measured.get("Sa_um", raw.get("sa"))),
        "processing_time_s": _none_or_float(measured.get("processing_time_s", raw.get("processing_time_s"))),
    }


def _normalize_qualitative_feedback(qualitative: dict[str, Any], raw: dict[str, Any], process_type: str = "milling") -> dict[str, str]:
    """Normalize qualitative feedback fields."""
    if process_type == "cutting":
        result = {
            "cut_through_level": "unknown",
            "kerf_width_level": "unknown",
            "edge_roughness_level": "unknown",
            "taper_level": "unknown",
            "chipping_level": "unknown",
            "efficiency_level": "unknown",
        }
        for key in list(result):
            result[key] = normalize_feedback_level(key, qualitative.get(key, raw.get(key)))
        return result
    result = QUALITATIVE_DEFAULTS.copy()
    aliases = {
        "roughness": qualitative.get("roughness", raw.get("roughness")),
        "depth": qualitative.get("depth", raw.get("depth_status")),
        "efficiency": qualitative.get("efficiency", raw.get("efficiency")),
    }
    for key, value in aliases.items():
        if value is None:
            continue
        result[key] = normalize_feedback_level(key, value)
    return result


def _model_available(material_data: pd.DataFrame, target: str) -> bool:
    """Return whether a surrogate can be fit for a target."""
    return int(material_data[target].notna().sum()) >= 5


def _material_data(data: pd.DataFrame, material: str, process_type: str = "milling") -> pd.DataFrame:
    """Select one material from the experiment table."""
    material_rows = data[data["material"].astype(str) == str(material)].copy()
    if material_rows.empty:
        raise ValueError(f"No rows found for material {material}")
    group = material_rows[material_rows["process_type"].fillna("milling") == process_type].copy()
    if group.empty and process_type == "cutting":
        return material_rows.iloc[0:0].copy()
    if group.empty:
        raise ValueError(f"No {process_type} rows found for material {material}")
    return add_engineered_features(group)


def _data_path(config_or_state: dict[str, Any]) -> Path:
    """Return the updated experiment data path."""
    if config_or_state.get("data_path"):
        return Path(config_or_state["data_path"])
    return _project_root(config_or_state) / "data" / "processed" / "updated_experiments.csv"


def _project_root(config_or_state: dict[str, Any]) -> Path:
    """Infer project root from config/state."""
    if config_or_state.get("_root"):
        return Path(config_or_state["_root"]).resolve()
    if config_or_state.get("project_root"):
        return Path(config_or_state["project_root"]).resolve()
    return Path.cwd()


def _output_dir(config_or_state: dict[str, Any]) -> Path:
    """Return output directory."""
    value = config_or_state.get("output_dir", "outputs")
    path = Path(value)
    return path if path.is_absolute() else _project_root(config_or_state) / path


def _posix_path_string(value: str | Path) -> str:
    """Return stable POSIX separators for relative paths stored in JSON."""
    return str(value).replace("\\", "/")


def _last_feedback(task_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the most recent non-empty feedback."""
    for item in reversed(task_state.get("history", [])):
        feedback = item.get("feedback")
        if feedback:
            return feedback
    return None


def _last_recommendation(task_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the most recent recommendation."""
    for item in reversed(task_state.get("history", [])):
        recommendation = item.get("recommendation")
        if recommendation:
            return recommendation
    return None


def _latest_iteration(task_state: dict[str, Any]) -> int:
    """Return the latest iteration number."""
    history = task_state.get("history", [])
    if not history:
        raise ValueError("No recommendation exists yet; run recommend first.")
    return int(history[-1]["iteration"])


def _history_item(task_state: dict[str, Any], iteration: int) -> dict[str, Any] | None:
    """Find one history item by iteration."""
    for item in task_state.get("history", []):
        if int(item.get("iteration", -1)) == int(iteration):
            return item
    return None


def _none_or_float(value: Any) -> float | None:
    """Convert optional numeric values to float."""
    if value is None or value == "":
        return None
    number = float(value)
    return number if np.isfinite(number) else None
