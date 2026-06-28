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
    for (material, target, model), group in predictions.groupby(["material", "target", "model"]):
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
        ax.set_title(f"{material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"pred_vs_true_{_safe_name(material, target, model)}.png")
        plt.close(fig)

        residual = pred[mask] - y[mask]
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        ax.scatter(pred[mask], residual, s=22, alpha=0.75)
        ax.axhline(0, color="black", linewidth=1)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Residual")
        ax.set_title(f"{material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"residual_{_safe_name(material, target, model)}.png")
        plt.close(fig)


def plot_feature_importance(importance: pd.DataFrame, figures_dir: Path) -> None:
    """Save bar plots for feature importance tables."""
    if importance.empty:
        return
    for (material, target, model, method), group in importance.groupby(["material", "target", "model", "method"]):
        top = group.sort_values("importance_rank").head(12)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
        ax.barh(top["feature"][::-1], top["importance_value"][::-1])
        ax.set_xlabel("Importance")
        ax.set_title(f"{material} {target} {model} {method}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"feature_importance_{_safe_name(material, target, model, method)}.png")
        plt.close(fig)


def plot_response_curve(curve: pd.DataFrame, figures_dir: Path) -> None:
    """Save univariate response curves."""
    if curve.empty:
        return
    for (material, target, model, feature), group in curve.groupby(["material", "target", "model", "feature"]):
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        ax.plot(group["feature_value"], group["prediction"], marker="o", linewidth=1.5)
        ax.set_xlabel(feature)
        ax.set_ylabel(f"Predicted {target}")
        ax.set_title(f"{material} {target} {model}")
        fig.tight_layout()
        fig.savefig(figures_dir / f"response_curve_{_safe_name(material, target, model, feature)}.png")
        plt.close(fig)


def plot_bo_maps(recommendations: pd.DataFrame, candidates: dict[str, pd.DataFrame], figures_dir: Path) -> None:
    """Plot 2D BO maps when scan speed and hatch spacing are available."""
    for material, cand in candidates.items():
        if cand.empty or not {"scan_speed_mm_s", "hatch_spacing_um", "objective_value"}.issubset(cand.columns):
            continue
        fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
        scatter = ax.scatter(cand["scan_speed_mm_s"], cand["hatch_spacing_um"], c=cand["objective_value"], s=15, cmap="viridis_r", alpha=0.5)
        rec = recommendations[recommendations["material"] == material]
        if not rec.empty:
            ax.scatter(rec["scan_speed_mm_s"], rec["hatch_spacing_um"], marker="*", s=120, color="red", edgecolor="black", linewidth=0.5)
        ax.set_xlabel("scan_speed_mm_s")
        ax.set_ylabel("hatch_spacing_um")
        ax.set_title(f"BO candidates {material}")
        fig.colorbar(scatter, ax=ax, label="objective")
        fig.tight_layout()
        fig.savefig(figures_dir / f"bo_recommendation_map_{_safe_name(material)}.png")
        plt.close(fig)
