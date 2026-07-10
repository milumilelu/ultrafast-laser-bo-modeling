from __future__ import annotations

from typing import Any


def validate_crl_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    required = ("radius_um", "aperture_um", "lens_count", "surface_count")
    missing = [name for name in required if geometry.get(name) is None]
    warnings = []
    if geometry.get("surface_count") not in {None, 2}:
        warnings.append("CRL domain pack expects a dual-paraboloid/two-surface geometry")
    for name in ("radius_um", "aperture_um", "lens_count"):
        value = geometry.get(name)
        if value is not None and float(value) <= 0:
            warnings.append(f"{name} must be positive")
    return {
        "valid": not missing and not warnings,
        "missing_fields": missing,
        "warnings": warnings,
        "geometry_type": "dual_paraboloid",
    }
