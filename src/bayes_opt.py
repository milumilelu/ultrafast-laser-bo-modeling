"""Offline Bayesian optimization recommendation using GPR surrogates."""

from __future__ import annotations

import itertools
import logging
from typing import Any

import numpy as np
import pandas as pd

from .features import add_engineered_features
from .models import FitResult


BO_COLUMNS = [
    "material",
    "rank",
    "recommendation_type",
    "pulse_width_ps",
    "frequency_kHz",
    "hatch_spacing_um",
    "passes",
    "scan_speed_mm_s",
    "predicted_depth_um",
    "predicted_depth_std_um",
    "predicted_Sa_um",
    "predicted_Sa_std_um",
    "objective_value",
    "acquisition_score",
    "roughness_model_available",
    "note",
]


BASE_PROCESS_FEATURES = ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s"]


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


def _choose_gpr(results: list[FitResult], material: str, target: str) -> FitResult | None:
    for result in results:
        if result.material == material and result.target == target and result.model_name == "GPR":
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


def generate_candidate_grid(material_data: pd.DataFrame, max_grid_size: int) -> pd.DataFrame:
    """Generate candidate points from observed parameter levels within observed ranges."""
    n_features = len(BASE_PROCESS_FEATURES)
    per_feature = max(2, int(np.floor(max_grid_size ** (1.0 / n_features))))
    level_lists = [_levels(material_data[col], per_feature) for col in BASE_PROCESS_FEATURES]
    if any(len(levels) == 0 for levels in level_lists):
        return pd.DataFrame(columns=BASE_PROCESS_FEATURES)
    combos = list(itertools.product(*level_lists))
    if len(combos) > max_grid_size:
        step = int(np.ceil(len(combos) / max_grid_size))
        combos = combos[::step][:max_grid_size]
    candidates = pd.DataFrame(combos, columns=BASE_PROCESS_FEATURES)
    return add_engineered_features(candidates)


def _score_candidates(
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
    configured_targets = config.get("target_depth_by_material", {}) or {}
    configured_sa_max = config.get("Sa_max_by_material", {}) or {}
    target_depth = configured_targets.get(material)
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
        sa_max = configured_sa_max.get(material)
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


def recommend_bo(
    data: pd.DataFrame,
    results: list[FitResult],
    config: dict[str, Any],
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Generate 5-10 offline BO recommendations per material using GPR surrogates."""
    n_recs = int(config.get("bo_n_recommendations", 5))
    n_recs = min(max(n_recs, 5), 10)
    grid_size = int(config.get("bo_candidate_grid_size", 3000))
    all_rows = []
    candidate_maps: dict[str, pd.DataFrame] = {}
    for material, group in data.groupby("material"):
        depth_model = _choose_gpr(results, material, "depth_um")
        if depth_model is None:
            logger.warning("Skipping BO for %s: no fitted GPR depth model", material)
            continue
        candidates = generate_candidate_grid(group[group["valid_flag"].astype(bool)], grid_size)
        if candidates.empty:
            logger.warning("Skipping BO for %s: no valid candidate grid", material)
            continue
        sa_model = _choose_gpr(results, material, "Sa_um")
        scored = _score_candidates(candidates, group, depth_model, sa_model, config)
        candidate_maps[material] = scored
        pools = []
        scored_valid = scored.dropna(subset=["objective_value", "predicted_depth_um"]).copy()
        if scored_valid.empty:
            continue
        scored_valid["recommendation_type"] = "exploitation"
        scored_valid["acquisition_score"] = -scored_valid["objective_value"]
        pools.append(scored_valid.sort_values("acquisition_score", ascending=False))
        explore = scored_valid.copy()
        explore["recommendation_type"] = "exploration"
        explore["acquisition_score"] = explore["predicted_depth_std_um"].fillna(0)
        pools.append(explore.sort_values("acquisition_score", ascending=False))
        balanced = scored_valid.copy()
        uncertainty = balanced["predicted_depth_std_um"].fillna(0)
        denom = max(float(uncertainty.max()), 1e-12)
        balanced["recommendation_type"] = "balanced"
        balanced["acquisition_score"] = -balanced["objective_value"] + 0.25 * uncertainty / denom
        pools.append(balanced.sort_values("acquisition_score", ascending=False))

        selected = []
        seen = set()
        for pool in pools:
            for _, row in pool.iterrows():
                key = tuple(row[col] for col in BASE_PROCESS_FEATURES)
                if key in seen:
                    continue
                seen.add(key)
                selected.append(row)
                if len(selected) >= n_recs:
                    break
            if len(selected) >= n_recs:
                break
        for rank, row in enumerate(selected, start=1):
            rec = {col: row.get(col, np.nan) for col in BO_COLUMNS}
            rec["material"] = material
            rec["rank"] = rank
            all_rows.append(rec)
    if not all_rows:
        return pd.DataFrame(columns=BO_COLUMNS), candidate_maps
    return pd.DataFrame(all_rows)[BO_COLUMNS], candidate_maps
