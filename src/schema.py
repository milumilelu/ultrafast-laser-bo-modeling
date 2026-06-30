"""Shared schema constants and normalization helpers for multi-process workflows."""

from __future__ import annotations

from typing import Any

import pandas as pd


PROCESS_TYPES = {"milling", "cutting"}
OBJECTIVE_MODES = {"quality_first", "efficiency_first", "balanced"}
MODEL_STATUSES = {"rule_based_cold_start", "hybrid_rule_bo", "data_driven_bo"}

FILL_PATTERNS = {"zigzag", "contour", "concentric", "polyline", "spiral", "none", "custom"}
FILL_PATTERN_LABELS = {
    "弓字形": "zigzag",
    "回字形": "contour",
    "回字形/轮廓": "contour",
    "轮廓": "contour",
    "轮廓线": "contour",
    "同心圆": "concentric",
    "折线": "polyline",
    "螺旋": "spiral",
    "无填充": "none",
    "单线切割": "none",
    "无填充/单线切割": "none",
    "自定义": "custom",
}
FILL_PATTERN_DISPLAY = {
    "zigzag": "弓字形",
    "contour": "回字形/轮廓",
    "concentric": "同心圆",
    "polyline": "折线",
    "spiral": "螺旋",
    "none": "无填充/单线切割",
    "custom": "自定义",
}

FEEDBACK_LEVEL_SCORE = {"很小": -2, "较小": -1, "适中": 0, "较大": 1, "很大": 2}
CUT_THROUGH_LEVEL_SCORE = {"未切透": -2, "勉强切透": -1, "适中": 0, "过烧蚀": 1, "严重过烧蚀": 2}

LEGACY_FEEDBACK_MAP = {
    "roughness": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "surface_roughness_level": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "edge_roughness_level": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "depth": {"acceptable": "适中", "too_shallow": "较小", "too_deep": "较大", "unknown": "unknown"},
    "depth_level": {"acceptable": "适中", "too_shallow": "较小", "too_deep": "较大", "unknown": "unknown"},
    "efficiency": {"acceptable": "适中", "too_low": "较小", "too_high": "较大", "unknown": "unknown"},
    "efficiency_level": {"acceptable": "适中", "too_low": "较小", "too_high": "较大", "unknown": "unknown"},
    "kerf_width_level": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "taper_level": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "chipping_level": {"acceptable": "适中", "too_large": "较大", "too_small": "较小", "unknown": "unknown"},
    "cut_through_level": {"acceptable": "适中", "too_low": "未切透", "too_high": "过烧蚀", "unknown": "unknown"},
}


def normalize_process_type(value: Any | None) -> str:
    """Normalize process type; missing legacy requests default to milling."""
    if _is_missing(value):
        return "milling"
    text = str(value).strip().lower()
    aliases = {"铣削": "milling", "面加工": "milling", "milling": "milling", "切割": "cutting", "cutting": "cutting"}
    normalized = aliases.get(text, text)
    if normalized not in PROCESS_TYPES:
        raise ValueError(f"Unsupported process_type: {value}")
    return normalized


def normalize_fill_pattern(value: Any | None) -> str:
    """Normalize Chinese or English fill-pattern labels to internal enums."""
    if _is_missing(value):
        return "none"
    text = str(value).strip()
    normalized = FILL_PATTERN_LABELS.get(text, text.lower())
    if normalized not in FILL_PATTERNS:
        raise ValueError(f"Unsupported fill_pattern: {value}")
    return normalized


def normalize_feedback_level(field: str, value: Any | None) -> str:
    """Normalize five-level and legacy qualitative feedback values."""
    if _is_missing(value):
        return "unknown"
    text = str(value).strip()
    text = LEGACY_FEEDBACK_MAP.get(field, {}).get(text, text)
    allowed = set(FEEDBACK_LEVEL_SCORE) | set(CUT_THROUGH_LEVEL_SCORE) | {"unknown"}
    if text not in allowed:
        raise ValueError(f"Unsupported feedback level {field}={value}")
    return text


def model_status_from_sample_count(n_valid_samples: int) -> str:
    """Return model status from process_type + material valid sample count."""
    if n_valid_samples < 10:
        return "rule_based_cold_start"
    if n_valid_samples < 30:
        return "hybrid_rule_bo"
    return "data_driven_bo"


def _is_missing(value: Any | None) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""
