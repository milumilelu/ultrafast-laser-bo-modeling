from __future__ import annotations

from typing import Any

from ultrafast_domain.domain_packs.base import DomainPack


def assess_aspect_ratio(geometry: dict[str, Any]) -> dict[str, Any]:
    thickness = geometry.get("wafer_thickness_um")
    diameter = geometry.get("hole_diameter_um")
    missing = [name for name, value in (("wafer_thickness_um", thickness), ("hole_diameter_um", diameter)) if value is None]
    if missing:
        return {"valid": False, "missing_fields": missing, "warnings": []}
    if float(diameter) <= 0 or float(thickness) <= 0:
        return {"valid": False, "missing_fields": [], "warnings": ["thickness and diameter must be positive"]}
    ratio = float(thickness) / float(diameter)
    return {"valid": True, "missing_fields": [], "warnings": [], "aspect_ratio": ratio, "high_aspect_ratio": ratio >= 5}


PACK = DomainPack(
    name="tgv",
    component_types=("TGV", "TGV_array", "through_glass_via"),
    quality_metrics=("taper_deg", "crack_length_um", "chipping_um", "through_rate", "yield"),
    process_constraints=("wafer_thickness_and_hole_diameter_required", "pitch_must_prevent_thermal_overlap", "online_monitoring_required_for_dense_arrays"),
    trial_templates={
        "simple_trial_cut": {"representative_geometry": "single_hole_or_3x3_array"},
        "full_trial_cut": {"representative_geometry": "full_density_array"},
    },
    measurement_templates={"hole": {"metrics": ["taper_deg", "crack_length_um", "chipping_um", "through_rate"]}},
    geometry_validator=assess_aspect_ratio,
)
