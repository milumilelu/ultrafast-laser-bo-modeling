"""Plotting utilities for model diagnostics and recommendations."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _safe_name(*parts: str) -> str:
    return "_".join(str(p).replace("/", "_").replace("\\", "_").replace(" ", "_") for p in parts)


def plot_pred_vs_true(predictions: pd.DataFrame, figures_dir: Path) -> None:
    """Save prediction-vs-true and residual plots for each model result."""
    group_cols = ["process_type", "material", "target", "model"] if "process_type" in predictions.columns else ["material", "target", "model"]
    for key, group in predictions.groupby(group_cols):
        if len(group_cols) == 4:
            process_type, material, target, model = key
        else:
            material, target, model = key
            process_type = "milling"
        y = group["y_true"].to_numpy(float)
        pred = group["y_pred_cv"].where(group["y_pred_cv"].notna(), group["y_pred_train"]).to_numpy(float)
        mask = np.isfinite(y) & np.isfinite(pred)
        if mask.sum() < 2:
            continue
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        ax.scatter(y[mask], pred[mask], s=22, alpha=0.75)
        lo, hi = min(y[mask].min(), pred[mask].min()), max(y[mask].max(), pred[mask].max())
        ax.plot([lo, hi], [lo, hi], color="black", linewidth=1)
        ax.set_xlabel("True")
        ax.set_ylabel("Predicted")
        ax.set_title(f"{process_type} {material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"pred_vs_true_{_safe_name(process_type, material, target, model)}.png")
        plt.close(fig)

        residual = pred[mask] - y[mask]
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        ax.scatter(pred[mask], residual, s=22, alpha=0.75)
        ax.axhline(0, color="black", linewidth=1)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Residual")
        ax.set_title(f"{process_type} {material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"residual_{_safe_name(process_type, material, target, model)}.png")
        plt.close(fig)


def plot_feature_importance(importance: pd.DataFrame, figures_dir: Path) -> None:
    """Save bar plots for feature importance tables."""
    if importance.empty:
        return
    group_cols = ["process_type", "material", "target", "model", "method"] if "process_type" in importance.columns else ["material", "target", "model", "method"]
    for key, group in importance.groupby(group_cols):
        if len(group_cols) == 5:
            process_type, material, target, model, method = key
        else:
            material, target, model, method = key
            process_type = "milling"
        top = group.sort_values("importance_rank").head(12)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        ax.barh(top["feature"][::-1], top["importance_value"][::-1])
        ax.set_xlabel("Importance")
        ax.set_title(f"{process_type} {material} {target} {model} {method}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"feature_importance_{_safe_name(process_type, material, target, model, method)}.png")
        plt.close(fig)


def plot_response_curve(curve: pd.DataFrame, figures_dir: Path) -> None:
    """Save univariate response curves."""
    if curve.empty:
        return
    group_cols = ["process_type", "material", "target", "model", "feature"] if "process_type" in curve.columns else ["material", "target", "model", "feature"]
    for key, group in curve.groupby(group_cols):
        if len(group_cols) == 5:
            process_type, material, target, model, feature = key
        else:
            material, target, model, feature = key
            process_type = "milling"
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        ax.plot(group["feature_value"], group["prediction"], marker="o", linewidth=1.5)
        ax.set_xlabel(feature)
        ax.set_ylabel(f"Predicted {target}")
        ax.set_title(f"{process_type} {material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"response_curve_{_safe_name(process_type, material, target, model, feature)}.png")
        plt.close(fig)


def plot_bo_maps(recommendations: pd.DataFrame, candidates: dict[str, pd.DataFrame], figures_dir: Path) -> None:
    """Plot 2D BO maps when scan speed and hatch spacing are available."""
    for key, cand in candidates.items():
        if cand.empty or not {"scan_speed_mm_s", "hatch_spacing_um", "objective_value"}.issubset(cand.columns):
            continue
        process_type, material = key.split("/", 1) if "/" in key else ("milling", key)
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        scatter = ax.scatter(cand["scan_speed_mm_s"], cand["hatch_spacing_um"], c=cand["objective_value"], s=15, cmap="viridis_r", alpha=0.5)
        rec = recommendations[(recommendations["process_type"] == process_type) & (recommendations["material"] == material)] if "process_type" in recommendations.columns else recommendations[recommendations["material"] == material]
        if not rec.empty:
            ax.scatter(rec["scan_speed_mm_s"], rec["hatch_spacing_um"], marker="*", s=120, color="red", edgecolor="black", linewidth=0.5)
        ax.set_xlabel("scan_speed_mm_s")
        ax.set_ylabel("hatch_spacing_um")
        ax.set_title(f"BO candidates {process_type} {material}")
        fig.colorbar(scatter, ax=ax, label="objective")
        fig.tight_layout()
        fig.savefig(figures_dir / f"bo_recommendation_map_{_safe_name(process_type, material)}.png")
        plt.close(fig)
