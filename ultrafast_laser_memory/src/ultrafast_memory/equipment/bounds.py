from __future__ import annotations

from typing import Any

from ultrafast_memory.core.config import load_config
from ultrafast_memory.equipment.service import get_active_equipment_profile, get_equipment_profile
from ultrafast_memory.equipment.validation import validate_override_within_bounds


REQUIRED_ACTIVE_BOUNDS = ("pulse_width_fs", "laser_power_W", "frequency_kHz", "scan_speed_mm_s", "spot_diameter_um")


def build_machine_bounds(equipment_profile_id: str | None = None) -> dict[str, Any]:
    profile = get_equipment_profile(equipment_profile_id) if equipment_profile_id else get_active_equipment_profile()
    if not profile:
        return {"active": False, "machine_bounds": {}, "missing_equipment_fields": list(REQUIRED_ACTIVE_BOUNDS)}
    bounds = _bounds_from_profile(profile)
    missing = _missing_equipment_fields(bounds)
    return {
        "active": True,
        "equipment_profile_id": profile["equipment_profile_id"],
        "profile_name": profile["profile_name"],
        "revision_id": profile.get("revision_id"),
        "machine_bounds": bounds,
        "missing_equipment_fields": missing,
    }


def require_machine_bounds_for_bo() -> dict[str, Any]:
    cfg = load_config().get("equipment", {})
    result = build_machine_bounds()
    if result.get("active"):
        return result
    if cfg.get("require_active_profile_for_bo", True):
        return {
            **result,
            "blocked": True,
            "message": "当前没有 active 设备配置，无法进行 BO 参数推荐。请先配置设备参数，或为本任务提供临时 machine_bounds。",
        }
    return result


def apply_task_level_override(machine_bounds: dict[str, Any], override: dict[str, Any], reason: str | None) -> dict[str, Any]:
    return validate_override_within_bounds(machine_bounds, override, reason)


def validate_candidate_within_bounds(candidate: dict[str, float | int], machine_bounds: dict[str, list[float | int]]) -> dict[str, Any]:
    violations = []
    for key, value in candidate.items():
        if key not in machine_bounds:
            continue
        lower, upper = machine_bounds[key]
        if float(value) < float(lower) or float(value) > float(upper):
            violations.append({"parameter": key, "value": value, "bounds": [lower, upper]})
    if violations:
        return {
            "valid": False,
            "invalid_reason": "blocked_by_machine_bounds",
            "violations": violations,
            "audit_trace": [{"step": "blocked_by_machine_bounds", "status": "invalid", "violations": violations}],
        }
    return {"valid": True, "violations": [], "audit_trace": []}


def _bounds_from_profile(profile: dict[str, Any]) -> dict[str, list[float | int]]:
    laser = profile.get("laser_source") or {}
    optical = profile.get("optical_setup") or {}
    motion = profile.get("motion_system") or {}
    process = profile.get("process_capability") or {}
    bounds: dict[str, list[float | int]] = {}
    _add_fixed(bounds, "wavelength_nm", laser.get("wavelength_nm"))
    if laser.get("pulse_width_fixed_fs") is not None:
        _add_fixed(bounds, "pulse_width_fs", laser.get("pulse_width_fixed_fs"))
    else:
        _add_range(bounds, "pulse_width_fs", laser.get("pulse_width_min_fs"), laser.get("pulse_width_max_fs"))
    if laser.get("actual_max_power_W") is not None:
        _add_range(bounds, "laser_power_W", 0, laser.get("actual_max_power_W"))
    else:
        _add_range(bounds, "laser_power_W", laser.get("average_power_min_W"), laser.get("average_power_max_W"))
    _add_range(bounds, "frequency_kHz", laser.get("frequency_min_kHz"), laser.get("frequency_max_kHz"))
    _add_fixed(bounds, "spot_diameter_um", optical.get("spot_diameter_um"))
    _add_range(bounds, "focus_offset_um", optical.get("focus_offset_min_um"), optical.get("focus_offset_max_um"))
    _add_range(bounds, "scan_speed_mm_s", motion.get("scan_speed_min_mm_s"), motion.get("scan_speed_max_mm_s"))
    _add_range(bounds, "hatch_spacing_um", process.get("hatch_spacing_min_um"), process.get("hatch_spacing_max_um"))
    _add_range(bounds, "layer_step_um", process.get("layer_step_min_um"), process.get("layer_step_max_um"))
    _add_range(bounds, "passes", process.get("passes_min"), process.get("passes_max"))
    return bounds


def _missing_equipment_fields(bounds: dict[str, Any]) -> list[str]:
    fields = []
    for key in REQUIRED_ACTIVE_BOUNDS:
        if key not in bounds:
            fields.append(key)
    return fields


def _add_fixed(bounds: dict[str, list[float | int]], key: str, value: Any) -> None:
    if value is not None:
        bounds[key] = [value, value]


def _add_range(bounds: dict[str, list[float | int]], key: str, lower: Any, upper: Any) -> None:
    if lower is not None and upper is not None:
        bounds[key] = [lower, upper]
