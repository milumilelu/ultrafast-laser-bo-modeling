"""Feature engineering for process-quality modeling."""

from __future__ import annotations

import numpy as np
import pandas as pd


BASE_FEATURES = [
    "pulse_width_ps",
    "frequency_kHz",
    "hatch_spacing_um",
    "passes",
    "scan_speed_mm_s",
    "power_W",
]

DERIVED_FEATURES = [
    "log_pulse_width",
    "log_frequency",
    "log_hatch_spacing",
    "log_passes",
    "log_scan_speed",
    "D_proxy",
    "pulse_energy_proxy",
    "energy_density_proxy",
]


def safe_log(series: pd.Series) -> pd.Series:
    """Compute log only for positive finite values; invalid values remain NaN."""
    values = pd.to_numeric(series, errors="coerce").astype(float)
    result = pd.Series(np.nan, index=series.index, dtype="float64")
    mask = values > 0
    result.loc[mask] = np.log(values.loc[mask])
    return result


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide two series while replacing zero and non-finite denominators with NaN."""
    num = pd.to_numeric(numerator, errors="coerce").astype(float)
    den = pd.to_numeric(denominator, errors="coerce").astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = num / den.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add log and proxy density features without introducing infinite values."""
    out = df.copy()
    for required in ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s", "power_W"]:
        if required not in out.columns:
            out[required] = np.nan
    out["log_pulse_width"] = safe_log(out["pulse_width_ps"])
    out["log_frequency"] = safe_log(out["frequency_kHz"])
    out["log_hatch_spacing"] = safe_log(out["hatch_spacing_um"])
    out["log_passes"] = safe_log(out["passes"])
    out["log_scan_speed"] = safe_log(out["scan_speed_mm_s"])
    denom = out["scan_speed_mm_s"] * out["hatch_spacing_um"]
    out["D_proxy"] = safe_divide(out["frequency_kHz"] * out["passes"], denom)
    out["pulse_energy_proxy"] = safe_divide(out["power_W"], out["frequency_kHz"])
    out["energy_density_proxy"] = safe_divide(out["power_W"] * out["passes"], denom)
    for col in DERIVED_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return out


def available_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return model feature columns that contain at least one observed value."""
    candidates = BASE_FEATURES + DERIVED_FEATURES
    return [col for col in candidates if col in df.columns and df[col].notna().any()]
