"""Acquisition scoring and qualitative feedback rules for interactive BO."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _finite_scale(values: pd.Series, fallback: float = 1.0) -> float:
    """Return a positive scale from observed values."""
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return fallback
    scale = float(clean.std())
    if not np.isfinite(scale) or scale <= 0:
        scale = abs(float(clean.median()))
    return max(scale, fallback)


def score_exploitation(scored: pd.DataFrame, objective_mode: str, context: dict[str, Any]) -> pd.Series:
    """Score candidates by predicted objective value only."""
    objective = compute_objective(scored, objective_mode, context)
    return -objective


def score_exploration(scored: pd.DataFrame, objective_mode: str, context: dict[str, Any]) -> pd.Series:
    """Score candidates by predictive uncertainty."""
    del objective_mode, context
    depth_std = pd.to_numeric(scored.get("predicted_depth_std_um", 0), errors="coerce").fillna(0)
    sa_std = pd.to_numeric(scored.get("predicted_Sa_std_um", 0), errors="coerce").fillna(0)
    return depth_std + 0.5 * sa_std


def score_balanced(scored: pd.DataFrame, objective_mode: str, context: dict[str, Any]) -> pd.Series:
    """Score candidates by objective value with a small uncertainty bonus."""
    exploitation = score_exploitation(scored, objective_mode, context)
    exploration = score_exploration(scored, objective_mode, context)
    denom = max(float(exploration.max()), 1e-12)
    return exploitation + 0.2 * exploration / denom


def compute_objective(scored: pd.DataFrame, objective_mode: str, context: dict[str, Any]) -> pd.Series:
    """Compute a minimization objective for the selected process goal."""
    depth = pd.to_numeric(scored["predicted_depth_um"], errors="coerce")
    sa = pd.to_numeric(scored.get("predicted_Sa_um"), errors="coerce")
    d_proxy = pd.to_numeric(scored.get("D_proxy"), errors="coerce").fillna(0)
    historical = context.get("historical_data", pd.DataFrame())
    target_depth = context.get("target_depth_um")
    depth_min = context.get("depth_min_um")
    sa_max = context.get("Sa_max_um")
    lambda_sa = float(context.get("lambda_sa", 0.25))
    sa_available = bool(context.get("roughness_model_available", False))

    depth_scale = _finite_scale(historical.get("depth_um", pd.Series(dtype=float)), fallback=max(abs(float(target_depth or 1.0)), 1.0))
    sa_scale = _finite_scale(historical.get("Sa_um", pd.Series(dtype=float)), fallback=1.0)
    d_scale = _finite_scale(historical.get("D_proxy", pd.Series(dtype=float)), fallback=1.0)

    if objective_mode == "quality_first":
        if sa_available:
            objective = sa / sa_scale
        else:
            objective = d_proxy / d_scale
        if depth_min is not None:
            objective = objective + np.maximum(0, float(depth_min) - depth) / depth_scale * 5
        elif target_depth is not None:
            objective = objective + np.maximum(0, float(target_depth) - depth) / depth_scale * 2
        return objective

    if objective_mode == "efficiency_first":
        objective = -depth / depth_scale
        if sa_available and sa_max is not None:
            objective = objective + np.maximum(0, sa - float(sa_max)) / sa_scale * 5
        return objective

    if target_depth is None:
        target_depth = float(historical["depth_um"].dropna().median()) if "depth_um" in historical and historical["depth_um"].notna().any() else 0.0
    objective = (depth - float(target_depth)).abs() / depth_scale
    if sa_available:
        objective = objective + lambda_sa * sa / sa_scale
    if depth_min is not None:
        objective = objective + np.maximum(0, float(depth_min) - depth) / depth_scale * 3
    if sa_available and sa_max is not None:
        objective = objective + np.maximum(0, sa - float(sa_max)) / sa_scale * 3
    return objective


def apply_qualitative_feedback_rules(
    scored: pd.DataFrame,
    feedback: dict[str, Any] | None,
    previous_parameters: dict[str, Any] | None,
) -> tuple[pd.DataFrame, str]:
    """Adjust candidate scores using qualitative feedback without creating labels."""
    if not feedback:
        return scored, "No qualitative feedback rule applied."
    out = scored.copy()
    out["rule_adjustment"] = 0.0
    notes: list[str] = []
    roughness = str(feedback.get("roughness", "unknown") or "unknown")
    depth = str(feedback.get("depth", "unknown") or "unknown")
    efficiency = str(feedback.get("efficiency", "unknown") or "unknown")
    previous_d = _previous_d_proxy(previous_parameters)
    d_proxy = pd.to_numeric(out.get("D_proxy"), errors="coerce")

    if roughness == "too_large":
        if previous_d is not None:
            out.loc[d_proxy > previous_d, "rule_adjustment"] -= 2.0 + (d_proxy[d_proxy > previous_d] - previous_d).fillna(0)
            out.loc[d_proxy <= previous_d, "rule_adjustment"] += 0.8
        out["rule_adjustment"] += out["scan_speed_mm_s"].rank(pct=True).fillna(0) * 0.25
        out["rule_adjustment"] += out["hatch_spacing_um"].rank(pct=True).fillna(0) * 0.25
        out["rule_adjustment"] -= out["passes"].rank(pct=True).fillna(0) * 0.25
        notes.append("Previous feedback indicated excessive roughness; candidates with lower D_proxy, fewer passes, higher scan speed, or wider hatch spacing were favored.")

    if depth == "too_shallow":
        if previous_d is not None:
            out.loc[d_proxy < previous_d, "rule_adjustment"] -= 2.0 + (previous_d - d_proxy[d_proxy < previous_d]).fillna(0)
            out.loc[d_proxy >= previous_d, "rule_adjustment"] += 0.8
        out["rule_adjustment"] += out["passes"].rank(pct=True).fillna(0) * 0.25
        out["rule_adjustment"] -= out["scan_speed_mm_s"].rank(pct=True).fillna(0) * 0.25
        out["rule_adjustment"] -= out["hatch_spacing_um"].rank(pct=True).fillna(0) * 0.25
        notes.append("Previous feedback indicated insufficient depth; candidates with higher D_proxy were favored.")

    if depth == "too_deep":
        if previous_d is not None:
            out.loc[d_proxy > previous_d, "rule_adjustment"] -= 1.5
            out.loc[d_proxy <= previous_d, "rule_adjustment"] += 0.5
        notes.append("Previous feedback indicated excessive depth; lower energy accumulation candidates were favored.")

    if efficiency == "too_low":
        out["rule_adjustment"] += out["scan_speed_mm_s"].rank(pct=True).fillna(0) * 0.35
        out["rule_adjustment"] -= out["passes"].rank(pct=True).fillna(0) * 0.35
        notes.append("Previous feedback indicated low efficiency; faster scan speed and fewer passes were favored when constraints allowed.")

    if roughness == "acceptable" and depth == "acceptable":
        if previous_d is not None:
            distance = (d_proxy - previous_d).abs()
            scale = max(float(distance.dropna().median()), 1e-12)
            out["rule_adjustment"] -= distance.fillna(scale) / scale * 0.1
        out["rule_adjustment"] += out["scan_speed_mm_s"].rank(pct=True).fillna(0) * 0.1
        notes.append("Previous quality and depth were acceptable; local exploitation near the last point was favored.")

    if "acquisition_score" in out:
        out["acquisition_score"] = out["acquisition_score"] + out["rule_adjustment"]
    reason = " ".join(notes) if notes else "Qualitative feedback did not match a directional rule."
    return out, reason


def _previous_d_proxy(params: dict[str, Any] | None) -> float | None:
    """Compute D_proxy for a previous recommendation."""
    if not params:
        return None
    try:
        frequency = float(params["frequency_kHz"])
        passes = float(params["passes"])
        speed = float(params["scan_speed_mm_s"])
        spacing = float(params["hatch_spacing_um"])
    except (KeyError, TypeError, ValueError):
        return None
    if speed <= 0 or spacing <= 0:
        return None
    value = frequency * passes / (speed * spacing)
    return float(value) if np.isfinite(value) else None
