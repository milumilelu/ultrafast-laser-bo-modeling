"""Process-specific objective and model-status helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def valid_sample_count(data: pd.DataFrame, process_type: str, material: str, target: str | None = None) -> int:
    """Count valid rows by process type, material, and optional target."""
    process = data.get("process_type", pd.Series(["milling"] * len(data), index=data.index)).fillna("milling")
    subset = data[(process == process_type) & (data["material"].astype(str) == str(material))]
    if "valid_flag" in subset.columns:
        subset = subset[subset["valid_flag"].astype(bool)]
    if target and target in subset.columns:
        subset = subset[subset[target].notna()]
    return int(len(subset))


def cutting_null_prediction() -> dict[str, Any]:
    """Return explicit null predictions for cutting cold start."""
    return {
        "cut_through_probability": None,
        "kerf_top_width_um": None,
        "kerf_bottom_width_um": None,
        "kerf_taper_deg": None,
        "cut_edge_Sa_um": None,
        "HAZ_width_um": None,
        "chipping_um": None,
    }


def finite_midpoint(bounds: Any, default: float | None = None) -> float | None:
    """Return a numeric midpoint from [min, max] bounds."""
    try:
        lo, hi = float(bounds[0]), float(bounds[1])
    except (TypeError, ValueError, IndexError):
        return default
    if not np.isfinite(lo) or not np.isfinite(hi):
        return default
    return (lo + hi) / 2
