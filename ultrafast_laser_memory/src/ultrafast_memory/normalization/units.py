from __future__ import annotations

ROUGHNESS_METRICS = {"ra", "sa", "sq", "roughness"}


def normalize_value(value: float, from_unit: str, quantity: str) -> tuple[float, str]:
    normalized, unit, _ = _normalize(value, from_unit, quantity)
    return normalized, unit


def normalize_measurement(value: float, from_unit: str, metric_name: str) -> tuple[float, str, bool]:
    metric = metric_name.lower()
    quantity = "roughness" if metric in ROUGHNESS_METRICS else metric
    return _normalize(value, from_unit, quantity)


def _normalize(value: float, from_unit: str, quantity: str) -> tuple[float, str, bool]:
    unit = (from_unit or "").strip().replace("μ", "u")
    q = (quantity or "").strip().lower().replace("_", "-")
    if q == "roughness":
        if unit == "nm":
            return value, "nm", True
        if unit == "um":
            return value * 1000.0, "nm", True
    if q in {"form-error", "depth", "hatch-spacing", "layer-step", "focus-offset"}:
        if unit == "um":
            return value, "um", True
        if unit == "nm":
            return value / 1000.0, "um", True
    if q == "frequency":
        if unit == "kHz":
            return value, "kHz", True
        if unit == "Hz":
            return value / 1000.0, "kHz", True
        if unit == "MHz":
            return value * 1000.0, "kHz", True
    if q == "pulse-width":
        if unit == "fs":
            return value, "fs", True
        if unit == "ps":
            return value * 1000.0, "fs", True
    if q == "scan-speed":
        if unit in {"mm/s", "mmps"}:
            return value, "mm/s", True
        if unit == "mm/min":
            return value / 60.0, "mm/s", True
    if q in {"laser-power", "power"} and unit == "W":
        return value, "W", True
    if q in {"duration"} and unit == "s":
        return value, "s", True
    return value, from_unit, False
