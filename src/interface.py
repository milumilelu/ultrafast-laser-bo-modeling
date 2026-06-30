"""JSON interface validation helpers for the multi-process recommendation API."""

from __future__ import annotations

from typing import Any

from .schema import normalize_feedback_level, normalize_fill_pattern, normalize_process_type


def validate_task_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a task request payload."""
    if "material" not in payload:
        raise ValueError("task_request.material is required")
    if "objective_mode" not in payload:
        raise ValueError("task_request.objective_mode is required")
    out = dict(payload)
    out["process_type"] = normalize_process_type(out.get("process_type"))
    bounds = dict(out.get("parameter_bounds") or {})
    if "fill_pattern" in bounds:
        bounds["fill_pattern"] = [normalize_fill_pattern(item) for item in bounds["fill_pattern"]]
    out["parameter_bounds"] = bounds
    return out


def validate_feedback(payload: dict[str, Any], process_type: str = "milling") -> dict[str, Any]:
    """Validate and normalize a feedback payload."""
    if "task_id" not in payload:
        raise ValueError("feedback.task_id is required")
    if "iteration" not in payload:
        raise ValueError("feedback.iteration is required")
    out = dict(payload)
    qualitative = dict(out.get("qualitative_feedback") or {})
    if normalize_process_type(process_type) == "milling":
        aliases = {
            "roughness": qualitative.get("roughness", qualitative.get("surface_roughness_level")),
            "depth": qualitative.get("depth", qualitative.get("depth_level")),
            "efficiency": qualitative.get("efficiency", qualitative.get("efficiency_level")),
        }
        out["qualitative_feedback"] = {field: normalize_feedback_level(field, value) for field, value in aliases.items() if value is not None}
        return out
    fields = ["cut_through_level", "kerf_width_level", "edge_roughness_level", "taper_level", "chipping_level", "efficiency_level"]
    out["qualitative_feedback"] = {field: normalize_feedback_level(field, qualitative.get(field)) for field in fields if field in qualitative}
    return out


def validate_recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate required recommendation fields."""
    for field in ["task_id", "process_type", "material", "model_status", "recommended_parameters", "prediction"]:
        if field not in payload:
            raise ValueError(f"recommendation.{field} is required")
    normalize_process_type(payload["process_type"])
    return payload
