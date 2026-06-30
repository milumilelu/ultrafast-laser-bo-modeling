"""Feature importance and response curve analysis."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from .models import FitResult


PREFERRED_RESPONSE_FEATURES = [
    "D_proxy",
    "pulse_density_proxy",
    "areal_energy_proxy",
    "line_energy_proxy",
    "pulse_spacing_um",
    "scan_speed_mm_s",
    "hatch_spacing_um",
    "laser_power_W",
    "layer_step_um",
    "frequency_kHz",
    "passes",
]


def _rsm_coefficient_importance(result: FitResult) -> pd.DataFrame:
    pipe = result.estimator
    if "poly" not in pipe.named_steps or "ridge" not in pipe.named_steps:
        return pd.DataFrame()
    poly = pipe.named_steps["poly"]
    ridge = pipe.named_steps["ridge"]
    names = poly.get_feature_names_out(result.feature_columns)
    coefs = np.abs(ridge.coef_)
    rows = []
    for feature in result.feature_columns:
        value = float(sum(coef for name, coef in zip(names, coefs) if feature in name.split(" ")))
        rows.append(
            {
                "process_type": result.process_type,
                "material": result.material,
                "target": result.target,
                "model": result.model_name,
                "feature": feature,
                "importance_value": value,
                "method": "RSM_abs_coefficient",
            }
        )
    df = pd.DataFrame(rows).sort_values("importance_value", ascending=False)
    df["importance_rank"] = range(1, len(df) + 1)
    return df


def _permutation_importance(result: FitResult, data: pd.DataFrame, random_seed: int, logger: logging.Logger) -> pd.DataFrame:
    subset = data.loc[data[result.target].notna() & data["valid_flag"].astype(bool)].copy()
    if len(subset) < 5:
        return pd.DataFrame()
    try:
        imp = permutation_importance(
            result.estimator,
            subset[result.feature_columns],
            subset[result.target],
            n_repeats=20,
            random_state=random_seed,
            scoring="neg_root_mean_squared_error",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Permutation importance failed for %s / %s / %s: %s", result.material, result.target, result.model_name, exc)
        return pd.DataFrame()
    rows = []
    for feature, value in zip(result.feature_columns, imp.importances_mean):
        rows.append(
            {
                "process_type": result.process_type,
                "material": result.material,
                "target": result.target,
                "model": result.model_name,
                "feature": feature,
                "importance_value": float(max(value, 0.0)),
                "method": "permutation_neg_RMSE",
            }
        )
    df = pd.DataFrame(rows).sort_values("importance_value", ascending=False)
    df["importance_rank"] = range(1, len(df) + 1)
    return df


def build_feature_importance(
    best_models: dict[tuple[str, str, str], FitResult],
    all_results: list[FitResult],
    data: pd.DataFrame,
    random_seed: int,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Build coefficient and permutation importance evidence tables."""
    frames = []
    for result in all_results:
        if result.model_name == "RSM":
            frames.append(_rsm_coefficient_importance(result))
    for result in best_models.values():
        subset = data[(data["process_type"].fillna("milling") == result.process_type) & (data["material"] == result.material)]
        frames.append(_permutation_importance(result, subset, random_seed, logger))
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=["process_type", "material", "target", "model", "feature", "importance_value", "importance_rank", "method"])
    return pd.concat(frames, ignore_index=True)


def build_response_curves(best_models: dict[tuple[str, str, str], FitResult], data: pd.DataFrame, n_points: int = 30) -> pd.DataFrame:
    """Build univariate response curves by varying one feature around observed medians."""
    rows = []
    for result in best_models.values():
        subset = data[
            (data["process_type"].fillna("milling") == result.process_type)
            & (data["material"] == result.material)
            & data[result.target].notna()
            & data["valid_flag"].astype(bool)
        ]
        if subset.empty:
            continue
        baseline = subset[result.feature_columns].median(numeric_only=True)
        for feature in [f for f in PREFERRED_RESPONSE_FEATURES if f in result.feature_columns]:
            values = pd.to_numeric(subset[feature], errors="coerce").dropna()
            if values.nunique() < 2:
                continue
            grid = np.linspace(values.min(), values.max(), n_points)
            x = pd.DataFrame([baseline.to_dict()] * len(grid))
            x[feature] = grid
            pred = result.estimator.predict(x[result.feature_columns])
            for value, yhat in zip(grid, pred):
                rows.append(
                    {
                        "process_type": result.process_type,
                        "material": result.material,
                        "target": result.target,
                        "model": result.model_name,
                        "feature": feature,
                        "feature_value": float(value),
                        "prediction": float(yhat),
                    }
                )
    return pd.DataFrame(rows)
