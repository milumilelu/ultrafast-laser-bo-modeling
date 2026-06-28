"""Model construction, fitting and cross-validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .evaluation import regression_metrics


@dataclass
class FitResult:
    """Container for one fitted model and its metadata."""

    material: str
    target: str
    model_name: str
    estimator: Any
    feature_columns: list[str]
    metrics: dict[str, float]
    predictions: pd.DataFrame


def _xgb_or_fallback(random_seed: int) -> tuple[str, Any]:
    try:
        from xgboost import XGBRegressor  # type: ignore

        return (
            "XGBoost",
            XGBRegressor(
                n_estimators=250,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                random_state=random_seed,
                n_jobs=1,
            ),
        )
    except Exception:  # noqa: BLE001
        return (
            "HistGradientBoosting",
            HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, random_state=random_seed),
        )


def build_model_specs(random_seed: int) -> dict[str, Any]:
    """Construct all requested model specifications."""
    kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=1.0, nu=2.5) + WhiteKernel(noise_level=1e-3)
    xgb_name, xgb_model = _xgb_or_fallback(random_seed)
    return {
        "RSM": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("poly", PolynomialFeatures(degree=2, include_bias=False)),
                ("ridge", Ridge(alpha=1.0)),
            ]
        ),
        "GPR": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("gpr", GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=random_seed, n_restarts_optimizer=2)),
            ]
        ),
        "RandomForest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("rf", RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=random_seed, n_jobs=-1)),
            ]
        ),
        xgb_name: Pipeline([("imputer", SimpleImputer(strategy="median")), ("boosting", xgb_model)]),
        "MLP": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("mlp", MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=1500, random_state=random_seed, early_stopping=True)),
            ]
        ),
    }


def _cv_predictions(estimator: Any, x: pd.DataFrame, y: pd.Series, max_folds: int, random_seed: int) -> tuple[np.ndarray, int]:
    """Generate cross-validated predictions with fold count adapted to sample size."""
    n = len(y)
    if n < 3:
        return np.full(n, np.nan), 0
    folds = min(max_folds, n)
    if folds < 2:
        return np.full(n, np.nan), 0
    cv = KFold(n_splits=folds, shuffle=True, random_state=random_seed)
    return cross_val_predict(clone(estimator), x, y, cv=cv, n_jobs=None), folds


def fit_models_for_target(
    data: pd.DataFrame,
    material: str,
    target: str,
    feature_columns: list[str],
    random_seed: int,
    cv_max_folds: int,
    logger: logging.Logger,
    min_samples: int = 8,
) -> list[FitResult]:
    """Fit requested models for one material-target pair."""
    subset = data.loc[data[target].notna() & data["valid_flag"].astype(bool)].copy()
    if len(subset) < min_samples:
        logger.warning("Skipping %s / %s: only %s valid samples; minimum is %s", material, target, len(subset), min_samples)
        return []
    usable_features = [c for c in feature_columns if c in subset.columns and subset[c].notna().any()]
    if not usable_features:
        logger.warning("Skipping %s / %s: no usable features", material, target)
        return []

    x = subset[usable_features]
    y = pd.to_numeric(subset[target], errors="coerce")
    specs = build_model_specs(random_seed)
    results: list[FitResult] = []
    for model_name, estimator in specs.items():
        try:
            cv_pred, folds = _cv_predictions(estimator, x, y, cv_max_folds, random_seed)
            fitted = clone(estimator).fit(x, y)
            train_pred = fitted.predict(x)
            train_metrics = regression_metrics(y, train_pred)
            cv_metrics = regression_metrics(y, cv_pred) if folds else {"MAE": np.nan, "RMSE": np.nan, "R2": np.nan}
            metrics = {
                "MAE": train_metrics["MAE"],
                "RMSE": train_metrics["RMSE"],
                "R2": train_metrics["R2"],
                "CV_MAE": cv_metrics["MAE"],
                "CV_RMSE": cv_metrics["RMSE"],
                "CV_R2": cv_metrics["R2"],
                "n_samples": int(len(y)),
                "n_features": int(len(usable_features)),
                "cv_folds": int(folds),
            }
            pred_df = pd.DataFrame(
                {
                    "material": material,
                    "target": target,
                    "model": model_name,
                    "row_index": subset.index,
                    "y_true": y.to_numpy(),
                    "y_pred_train": train_pred,
                    "y_pred_cv": cv_pred,
                }
            )
            results.append(FitResult(material, target, model_name, fitted, usable_features, metrics, pred_df))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping model %s for %s / %s: %s", model_name, material, target, exc)
    return results


def summarize_performance(results: list[FitResult]) -> pd.DataFrame:
    """Convert fitted model results to a performance table."""
    rows = []
    for result in results:
        row = {"material": result.material, "target": result.target, "model": result.model_name}
        row.update(result.metrics)
        rows.append(row)
    return pd.DataFrame(rows)


def select_best_models(results: list[FitResult]) -> dict[tuple[str, str], FitResult]:
    """Select the best model for each material-target pair by CV_RMSE, excluding MLP when alternatives exist."""
    best: dict[tuple[str, str], FitResult] = {}
    grouped: dict[tuple[str, str], list[FitResult]] = {}
    for result in results:
        grouped.setdefault((result.material, result.target), []).append(result)
    for key, items in grouped.items():
        candidates = [r for r in items if r.model_name != "MLP"] or items
        candidates = sorted(candidates, key=lambda r: (np.inf if pd.isna(r.metrics.get("CV_RMSE")) else r.metrics["CV_RMSE"], r.metrics["RMSE"]))
        best[key] = candidates[0]
    return best
