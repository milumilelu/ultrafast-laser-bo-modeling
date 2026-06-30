"""Offline Bayesian optimization recommendations isolated by process type."""

from __future__ import annotations

import itertools
import logging
from typing import Any

import numpy as np
import pandas as pd

from .features import add_engineered_features
from .models import FitResult


MILLING_TARGETS = ["depth_um", "Sa_um"]
CUTTING_TARGETS = ["cut_through", "kerf_top_width_um", "kerf_taper_deg", "cut_edge_Sa_um", "chipping_um"]
PROCESS_NUMERIC_FEATURES = {
    "milling": ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s", "laser_power_W", "focus_offset_um", "layer_step_um"],
    "cutting": ["pulse_width_ps", "frequency_kHz", "laser_power_W", "scan_speed_mm_s", "passes", "focus_offset_um", "layer_step_um", "hatch_spacing_um"],
}

BO_COLUMNS = [
    "process_type",
    "material",
    "rank",
    "recommendation_type",
    "pulse_width_ps",
    "frequency_kHz",
    "laser_power_W",
    "hatch_spacing_um",
    "passes",
    "scan_speed_mm_s",
    "focus_offset_um",
    "layer_step_um",
    "fill_pattern",
    "predicted_depth_um",
    "predicted_depth_std_um",
    "predicted_Sa_um",
    "predicted_Sa_std_um",
    "predicted_cut_through",
    "predicted_cut_through_std",
    "predicted_kerf_top_width_um",
    "predicted_kerf_taper_deg",
    "predicted_cut_edge_Sa_um",
    "predicted_chipping_um",
    "objective_value",
    "acquisition_score",
    "roughness_model_available",
    "note",
]


def _map_key(process_type: str, material: str) -> str:
    return f"{process_type}/{material}"


def _predict_with_std(result: FitResult | None, x: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    if result is None:
        n = len(x)
        return np.full(n, np.nan), np.full(n, np.nan)
    if result.model_name == "GPR" and hasattr(result.estimator, "named_steps"):
        pipe = result.estimator
        transformed = pipe[:-1].transform(x[result.feature_columns])
        mean, std = pipe.named_steps["gpr"].predict(transformed, return_std=True)
        return np.asarray(mean, dtype=float), np.asarray(std, dtype=float)
    mean = result.estimator.predict(x[result.feature_columns])
    return np.asarray(mean, dtype=float), np.full(len(x), np.nan)


def _choose_gpr(results: list[FitResult], process_type: str, material: str, target: str) -> FitResult | None:
    for result in results:
        if result.process_type == process_type and result.material == material and result.target == target and result.model_name == "GPR":
            return result
    return None


def _levels(values: pd.Series, per_feature_size: int) -> list[float]:
    observed = np.sort(pd.to_numeric(values, errors="coerce").dropna().unique())
    if len(observed) == 0:
        return []
    if len(observed) <= per_feature_size:
        return [float(v) for v in observed]
    idx = np.linspace(0, len(observed) - 1, per_feature_size).round().astype(int)
    return [float(v) for v in observed[idx]]


def _candidate_numeric_features(process_type: str, group: pd.DataFrame) -> list[str]:
    features = []
    for col in PROCESS_NUMERIC_FEATURES.get(process_type, PROCESS_NUMERIC_FEATURES["milling"]):
        if col in group.columns and pd.to_numeric(group[col], errors="coerce").notna().any():
            features.append(col)
    return features


def generate_candidate_grid(process_data: pd.DataFrame, process_type: str, max_grid_size: int) -> pd.DataFrame:
    """Generate candidates from observed levels for one process/material group."""
    numeric_features = _candidate_numeric_features(process_type, process_data)
    if not numeric_features:
        return pd.DataFrame()
    per_feature = max(2, int(np.floor(max_grid_size ** (1.0 / len(numeric_features)))))
    level_lists = [_levels(process_data[col], per_feature) for col in numeric_features]
    if any(len(levels) == 0 for levels in level_lists):
        return pd.DataFrame(columns=numeric_features)
    combos = list(itertools.product(*level_lists))

    fill_choices = []
    if "fill_pattern" in process_data.columns and process_data["fill_pattern"].notna().any():
        fill_choices = sorted(str(v) for v in process_data["fill_pattern"].dropna().unique())[:4]
    if fill_choices:
        combos = [combo + (fill,) for combo, fill in itertools.product(combos, fill_choices)]
        columns = numeric_features + ["fill_pattern"]
    else:
        columns = numeric_features

    if len(combos) > max_grid_size:
        step = int(np.ceil(len(combos) / max_grid_size))
        combos = combos[::step][:max_grid_size]
    candidates = pd.DataFrame(combos, columns=columns)
    candidates["process_type"] = process_type
    return add_engineered_features(candidates)


def _config_lookup(config: dict[str, Any], key: str, process_type: str, material: str) -> Any:
    values = config.get(key, {}) or {}
    return values.get(f"{process_type}:{material}", values.get(material))


def _score_milling_candidates(
    candidates: pd.DataFrame,
    material_data: pd.DataFrame,
    depth_model: FitResult,
    sa_model: FitResult | None,
    config: dict[str, Any],
) -> pd.DataFrame:
    depth_mean, depth_std = _predict_with_std(depth_model, candidates)
    sa_mean, sa_std = _predict_with_std(sa_model, candidates)
    out = candidates.copy()
    out["predicted_depth_um"] = depth_mean
    out["predicted_depth_std_um"] = depth_std
    out["predicted_Sa_um"] = sa_mean
    out["predicted_Sa_std_um"] = sa_std
    material = depth_model.material
    process_type = depth_model.process_type
    target_depth = _config_lookup(config, "target_depth_by_material", process_type, material)
    note = []
    if target_depth is None:
        target_depth = float(material_data["depth_um"].dropna().median())
        note.append("target_depth not configured; using observed median depth")
    depth_scale = max(float(material_data["depth_um"].dropna().std()), abs(float(target_depth)), 1.0)

    sa_scale = 1.0
    if sa_model is not None and material_data["Sa_um"].notna().any():
        sa_scale = max(float(material_data["Sa_um"].dropna().median()), 1.0)

    mode = config.get("bo_mode", "target_depth_min_sa")
    lambda_sa = float(config.get("lambda_sa", 0.25))
    if mode == "constrained_depth":
        sa_max = _config_lookup(config, "Sa_max_by_material", process_type, material)
        if sa_max is None and material_data["Sa_um"].notna().any():
            sa_max = float(material_data["Sa_um"].dropna().median())
            note.append("Sa_max not configured; using observed median Sa")
        feasible = np.ones(len(out), dtype=bool)
        if sa_model is not None and sa_max is not None:
            feasible = out["predicted_Sa_um"] <= float(sa_max)
        objective = -out["predicted_depth_um"].where(feasible, -np.inf)
    else:
        objective = np.abs(out["predicted_depth_um"] - float(target_depth)) / depth_scale
        if sa_model is not None:
            objective = objective + lambda_sa * out["predicted_Sa_um"] / sa_scale
        else:
            note.append("roughness model unavailable; depth-only recommendation")
    out["objective_value"] = objective.replace([np.inf, -np.inf], np.nan)
    out["roughness_model_available"] = sa_model is not None
    out["note"] = "; ".join(dict.fromkeys(note))
    return out


def _score_cutting_candidates(candidates: pd.DataFrame, models: dict[str, FitResult | None], config: dict[str, Any]) -> pd.DataFrame:
    out = candidates.copy()
    note = []
    objective = pd.Series(0.0, index=out.index)
    for target in CUTTING_TARGETS:
        model = models.get(target)
        mean, std = _predict_with_std(model, candidates)
        if target == "cut_through":
            out["predicted_cut_through"] = mean
            out["predicted_cut_through_std"] = std
            if model is not None:
                objective = objective - pd.Series(mean, index=out.index).clip(0, 1).fillna(0)
            else:
                note.append("cut_through model unavailable")
        elif target == "kerf_top_width_um":
            out["predicted_kerf_top_width_um"] = mean
            if model is not None:
                objective = objective + _normalized(mean)
            else:
                note.append("kerf width model unavailable")
        elif target == "kerf_taper_deg":
            out["predicted_kerf_taper_deg"] = mean
            if model is not None:
                objective = objective + _normalized(mean)
            else:
                note.append("taper model unavailable")
        elif target == "cut_edge_Sa_um":
            out["predicted_cut_edge_Sa_um"] = mean
            if model is not None:
                objective = objective + _normalized(mean)
            else:
                note.append("edge roughness model unavailable")
        elif target == "chipping_um":
            out["predicted_chipping_um"] = mean
            if model is not None:
                objective = objective + _normalized(mean)
            else:
                note.append("chipping model unavailable")
    if "scan_speed_mm_s" in out.columns:
        speed = pd.to_numeric(out["scan_speed_mm_s"], errors="coerce")
        objective = objective - 0.05 * speed.fillna(speed.median()) / max(float(speed.max()), 1.0)
    out["objective_value"] = objective.replace([np.inf, -np.inf], np.nan)
    out["roughness_model_available"] = models.get("cut_edge_Sa_um") is not None
    out["note"] = "; ".join(dict.fromkeys(note))
    return out


def _normalized(values: np.ndarray) -> pd.Series:
    series = pd.Series(values, dtype="float64")
    scale = max(float(series.dropna().median()) if series.notna().any() else 1.0, 1.0)
    return series / scale


def _select_rows(scored: pd.DataFrame, process_type: str, n_recs: int) -> list[pd.Series]:
    scored_valid = scored.dropna(subset=["objective_value"]).copy()
    if process_type == "milling":
        scored_valid = scored_valid.dropna(subset=["predicted_depth_um"])
    if scored_valid.empty:
        return []
    pools = []
    scored_valid["recommendation_type"] = "exploitation"
    scored_valid["acquisition_score"] = -scored_valid["objective_value"]
    pools.append(scored_valid.sort_values("acquisition_score", ascending=False))
    explore = scored_valid.copy()
    uncertainty_cols = [col for col in ["predicted_depth_std_um", "predicted_cut_through_std"] if col in explore.columns]
    explore_uncertainty = explore[uncertainty_cols].fillna(0).sum(axis=1) if uncertainty_cols else pd.Series(0.0, index=explore.index)
    explore["recommendation_type"] = "exploration"
    explore["acquisition_score"] = explore_uncertainty
    pools.append(explore.sort_values("acquisition_score", ascending=False))
    balanced = scored_valid.copy()
    denom = max(float(explore_uncertainty.max()), 1e-12)
    balanced["recommendation_type"] = "balanced"
    balanced["acquisition_score"] = -balanced["objective_value"] + 0.25 * explore_uncertainty / denom
    pools.append(balanced.sort_values("acquisition_score", ascending=False))

    parameter_cols = [col for col in PROCESS_NUMERIC_FEATURES.get(process_type, []) + ["fill_pattern"] if col in scored_valid.columns]
    selected = []
    seen = set()
    for pool in pools:
        for _, row in pool.iterrows():
            key = tuple(row.get(col) for col in parameter_cols)
            if key in seen:
                continue
            seen.add(key)
            selected.append(row)
            if len(selected) >= n_recs:
                break
        if len(selected) >= n_recs:
            break
    return selected


def recommend_bo(
    data: pd.DataFrame,
    results: list[FitResult],
    config: dict[str, Any],
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Generate offline BO recommendations per process_type + material group."""
    n_recs = int(config.get("bo_n_recommendations", 5))
    n_recs = min(max(n_recs, 5), 10)
    grid_size = int(config.get("bo_candidate_grid_size", 3000))
    all_rows = []
    candidate_maps: dict[str, pd.DataFrame] = {}
    process_series = data.get("process_type", pd.Series("milling", index=data.index)).fillna("milling")
    for (process_type, material), group in data.assign(process_type=process_series).groupby(["process_type", "material"]):
        valid_group = group[group["valid_flag"].astype(bool)]
        if process_type == "cutting":
            target_models = {target: _choose_gpr(results, process_type, material, target) for target in CUTTING_TARGETS}
            if not any(target_models.values()):
                logger.warning("Skipping BO for %s / %s: no fitted cutting GPR models", process_type, material)
                continue
            candidates = generate_candidate_grid(valid_group, process_type, grid_size)
            if candidates.empty:
                logger.warning("Skipping BO for %s / %s: no valid candidate grid", process_type, material)
                continue
            scored = _score_cutting_candidates(candidates, target_models, config)
        else:
            depth_model = _choose_gpr(results, process_type, material, "depth_um")
            if depth_model is None:
                logger.warning("Skipping BO for %s / %s: no fitted GPR depth model", process_type, material)
                continue
            candidates = generate_candidate_grid(valid_group, process_type, grid_size)
            if candidates.empty:
                logger.warning("Skipping BO for %s / %s: no valid candidate grid", process_type, material)
                continue
            sa_model = _choose_gpr(results, process_type, material, "Sa_um")
            scored = _score_milling_candidates(candidates, group, depth_model, sa_model, config)
        key = _map_key(process_type, material)
        scored["process_type"] = process_type
        candidate_maps[key] = scored
        selected = _select_rows(scored, process_type, n_recs)
        for rank, row in enumerate(selected, start=1):
            rec = {col: row.get(col, np.nan) for col in BO_COLUMNS}
            rec["process_type"] = process_type
            rec["material"] = material
            rec["rank"] = rank
            all_rows.append(rec)
    if not all_rows:
        return pd.DataFrame(columns=BO_COLUMNS), candidate_maps
    return pd.DataFrame(all_rows)[BO_COLUMNS], candidate_maps
