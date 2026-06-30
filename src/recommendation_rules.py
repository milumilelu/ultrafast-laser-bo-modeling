"""Rule-based cold-start recommendations for process-specific feedback."""

from __future__ import annotations

from typing import Any

import numpy as np

from .objectives import cutting_null_prediction, finite_midpoint
from .schema import CUT_THROUGH_LEVEL_SCORE, FEEDBACK_LEVEL_SCORE, normalize_fill_pattern


def cold_start_cutting_parameters(bounds: dict[str, Any] | None, requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate conservative cutting parameters within user bounds."""
    bounds = bounds or {}
    requirements = requirements or {}
    params = {
        "pulse_width_ps": finite_midpoint(bounds.get("pulse_width_ps", [0.3, 10]), 10),
        "frequency_kHz": finite_midpoint(bounds.get("frequency_kHz", [50, 500]), 200),
        "laser_power_W": finite_midpoint(bounds.get("laser_power_W", [1, 20]), 5),
        "scan_speed_mm_s": finite_midpoint(bounds.get("scan_speed_mm_s", [10, 1000]), 100),
        "passes": round(finite_midpoint(bounds.get("passes", [1, 30]), 5) or 5),
        "focus_offset_um": finite_midpoint(bounds.get("focus_offset_um", [-100, 100]), 0),
        "layer_step_um": finite_midpoint(bounds.get("layer_step_um", [1, 20]), 5),
        "hatch_spacing_um": None,
        "fill_pattern": "none",
    }
    if bounds.get("fill_pattern"):
        choices = [normalize_fill_pattern(item) for item in bounds["fill_pattern"]]
        params["fill_pattern"] = "none" if "none" in choices else choices[0]
    if requirements.get("material_thickness_um") and params["layer_step_um"]:
        estimated_layers = int(np.ceil(float(requirements["material_thickness_um"]) / float(params["layer_step_um"])))
        params["passes"] = max(int(params["passes"]), min(estimated_layers, int(_upper(bounds.get("passes", [1, 30]), 30))))
    return clamp_parameters(params, bounds)


def apply_cutting_feedback_to_parameters(
    previous: dict[str, Any],
    feedback: dict[str, Any],
    bounds: dict[str, Any] | None,
    objective_mode: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Adjust cutting parameters from qualitative feedback without fabricating labels."""
    bounds = bounds or {}
    params = dict(previous)
    interp = interpret_cutting_feedback(feedback, objective_mode)
    increase = float(interp["increase_energy_strength"])
    decrease = float(interp["decrease_energy_strength"])
    resolution = interp["suggested_direction"]["resolution"]
    if resolution.startswith("quality_first"):
        decrease *= 1.3
        increase *= 0.6
    elif resolution.startswith("efficiency_first"):
        increase *= 1.2
        decrease *= 0.8

    if increase > 0:
        _scale(params, "laser_power_W", 1 + 0.10 * increase)
        _scale(params, "scan_speed_mm_s", max(0.1, 1 - 0.08 * increase))
        params["passes"] = float(params.get("passes") or 1) + max(1, round(increase))
        _scale(params, "layer_step_um", max(0.1, 1 - 0.06 * increase))
    if decrease > 0:
        _scale(params, "laser_power_W", max(0.1, 1 - 0.10 * decrease))
        _scale(params, "scan_speed_mm_s", 1 + 0.08 * decrease)
        params["passes"] = max(1, float(params.get("passes") or 1) - max(1, round(decrease)))
        _scale(params, "layer_step_um", 1 + 0.06 * decrease)
    params = clamp_parameters(params, bounds)
    return params, interp, cutting_reason(interp)


def interpret_cutting_feedback(feedback: dict[str, Any], objective_mode: str) -> dict[str, Any]:
    """Map cutting feedback into directional strengths."""
    cut_level = feedback.get("cut_through_level", "unknown")
    kerf_level = feedback.get("kerf_width_level", "unknown")
    edge_level = feedback.get("edge_roughness_level", "unknown")
    taper_level = feedback.get("taper_level", "unknown")
    chipping_level = feedback.get("chipping_level", "unknown")
    efficiency_level = feedback.get("efficiency_level", "unknown")
    increase = 0
    decrease = 0
    reasons: list[str] = []
    cut_score = CUT_THROUGH_LEVEL_SCORE.get(cut_level)
    if cut_score is not None and cut_score < 0:
        increase += abs(cut_score)
        reasons.append("cut_not_enough_increase_energy")
    if cut_score is not None and cut_score > 0:
        decrease += cut_score
        reasons.append("overburn_decrease_energy")
    for name, level in [("kerf_width", kerf_level), ("edge_roughness", edge_level), ("taper", taper_level), ("chipping", chipping_level)]:
        score = FEEDBACK_LEVEL_SCORE.get(level)
        if score is not None and score > 0:
            decrease += score
            reasons.append(f"{name}_large_decrease_heat_input")
    eff_score = FEEDBACK_LEVEL_SCORE.get(efficiency_level)
    if eff_score is not None and eff_score < 0:
        increase += abs(eff_score)
        reasons.append("efficiency_small_increase_process_intensity")
    conflict = increase > 0 and decrease > 0
    if conflict and objective_mode == "quality_first":
        resolution = "quality_first_prioritize_edge_quality_and_cut_through_constraint"
    elif conflict and objective_mode == "efficiency_first":
        resolution = "efficiency_first_prioritize_cut_through_with_quality_constraint"
    elif conflict:
        resolution = "balanced_tradeoff"
    else:
        resolution = "single_direction"
    if conflict:
        direction = "increase_for_cut_through_or_efficiency_but_decrease_for_quality"
    elif increase:
        direction = "increase_cutting_intensity"
    elif decrease:
        direction = "decrease_heat_input"
    else:
        direction = "local_or_no_directional_change"
    return {
        "cut_through_level": cut_level,
        "kerf_width_level": kerf_level,
        "edge_roughness_level": edge_level,
        "taper_level": taper_level,
        "chipping_level": chipping_level,
        "efficiency_level": efficiency_level,
        "cut_through_score": cut_score,
        "increase_energy_strength": int(increase),
        "decrease_energy_strength": int(decrease),
        "suggested_direction": {"cutting_intensity": direction, "conflict": conflict, "resolution": resolution, "raw_reasons": reasons},
    }


def cutting_reason(interp: dict[str, Any]) -> str:
    """Build a short cold-start cutting explanation."""
    direction = interp["suggested_direction"]
    return (
        "No valid cutting data available. Recommendation generated by conservative cold-start rules within bounds. "
        f"Direction: {direction['cutting_intensity']}; resolution: {direction['resolution']}."
    )


def cutting_prediction_nulls() -> dict[str, Any]:
    """Return null cutting prediction payload."""
    return cutting_null_prediction()


def clamp_parameters(params: dict[str, Any], bounds: dict[str, Any] | None) -> dict[str, Any]:
    """Clamp numeric parameters to supplied bounds."""
    out = dict(params)
    for key, value in list(out.items()):
        if value is None or key == "fill_pattern":
            continue
        bound = (bounds or {}).get(key)
        if isinstance(bound, (list, tuple)) and len(bound) == 2:
            try:
                out[key] = min(max(float(value), float(bound[0])), float(bound[1]))
            except (TypeError, ValueError):
                pass
    if out.get("passes") is not None:
        out["passes"] = int(max(1, round(float(out["passes"]))))
    return out


def _scale(params: dict[str, Any], key: str, factor: float) -> None:
    if params.get(key) is not None:
        params[key] = float(params[key]) * factor


def _upper(bounds: Any, default: float) -> float:
    try:
        return float(bounds[1])
    except (TypeError, ValueError, IndexError):
        return default
