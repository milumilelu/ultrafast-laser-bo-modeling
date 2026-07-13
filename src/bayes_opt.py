"""Offline recommendations routed through the governed BO application service."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from ultrafast_bo.application.formal_service import BORecommendationService
from ultrafast_bo.domain.models import BOSample

from .models import FitResult


MILLING_TARGETS = ["depth_um", "Sa_um"]
CUTTING_TARGETS = ["cut_through", "kerf_top_width_um", "kerf_taper_deg", "cut_edge_Sa_um", "chipping_um"]
PROCESS_NUMERIC_FEATURES = {
    "milling": ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s", "laser_power_W", "focus_offset_um", "layer_step_um"],
    "cutting": ["pulse_width_ps", "frequency_kHz", "laser_power_W", "scan_speed_mm_s", "passes", "focus_offset_um", "layer_step_um", "hatch_spacing_um"],
}

BO_COLUMNS = [
    "process_type", "material", "rank", "recommendation_type",
    "pulse_width_ps", "frequency_kHz", "laser_power_W", "hatch_spacing_um",
    "passes", "scan_speed_mm_s", "focus_offset_um", "layer_step_um", "fill_pattern",
    "predicted_depth_um", "predicted_depth_std_um", "predicted_Sa_um", "predicted_Sa_std_um",
    "predicted_cut_through", "predicted_cut_through_std", "predicted_kerf_top_width_um",
    "predicted_kerf_taper_deg", "predicted_cut_edge_Sa_um", "predicted_chipping_um",
    "objective_value", "acquisition_score", "roughness_model_available", "note",
]


def recommend_bo(
    data: pd.DataFrame,
    results: list[FitResult],
    config: dict[str, Any],
    logger: logging.Logger,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Return scoped recommendations; legacy tables are presentation only.

    ``results`` is retained as a compatibility gate: a group is recommended only
    after the existing offline fitting stage proved that its objective is usable.
    Model fitting, acquisition and selection are performed solely by
    :class:`BORecommendationService`.
    """
    n_recs = min(max(int(config.get("bo_n_recommendations", 5)), 5), 10)
    base_seed = int(config.get("random_seed", 42))
    candidate_count = min(max(int(config.get("bo_candidate_grid_size", 256)), 32), 4096)
    process_series = data.get("process_type", pd.Series("milling", index=data.index)).fillna("milling")
    fitted = {(str(item.process_type), str(item.material), str(item.target)) for item in results if item.model_name == "GPR"}
    rows: list[dict[str, Any]] = []
    candidate_maps: dict[str, pd.DataFrame] = {}

    for (process_type, material), raw_group in data.assign(process_type=process_series).groupby(["process_type", "material"]):
        process_type, material = str(process_type), str(material)
        target = _select_objective(fitted, process_type, material)
        if target is None:
            logger.warning("Skipping governed BO for %s / %s: no fitted objective model", process_type, material)
            continue
        group = raw_group[_truthy_series(raw_group.get("valid_flag", pd.Series(True, index=raw_group.index)))].copy()
        bounds = _observed_bounds(group, process_type)
        samples = _samples(group, process_type, material, target, bounds)
        if not bounds or len(samples) < 5:
            logger.warning("Skipping governed BO for %s / %s: insufficient scoped numeric data", process_type, material)
            continue

        service = BORecommendationService()
        selected: list[dict[str, Any]] = []
        seen: set[tuple[tuple[str, Any], ...]] = set()
        for offset in range(max(n_recs * 3, n_recs)):
            response = service.recommend(
                {
                    "material": material,
                    "process_type": process_type,
                    "objective_metric": target,
                    "random_seed": base_seed + offset,
                    "optimizer_restarts": 0,
                    "candidate_count": candidate_count,
                    "code_version": "offline-compatibility-entrypoint",
                },
                samples,
                {
                    "active": True,
                    "equipment_profile_id": "offline-observed-scope",
                    "revision_id": "offline-observed-bounds-v1",
                    "machine_bounds": bounds,
                },
            )
            parameters = response.get("recommended_parameters") or {}
            if response.get("status") == "blocked" or not parameters:
                logger.warning("Governed BO blocked for %s / %s: %s", process_type, material, response.get("blocking_reasons"))
                break
            key = tuple(sorted(parameters.items()))
            if key in seen:
                continue
            seen.add(key)
            selected.append(_legacy_row(response, parameters, process_type, material, target, len(selected) + 1))
            if len(selected) >= n_recs:
                break

        if selected:
            frame = pd.DataFrame(selected)
            candidate_maps[f"{process_type}/{material}"] = frame.copy()
            rows.extend(selected)

    if not rows:
        return pd.DataFrame(columns=BO_COLUMNS), candidate_maps
    return pd.DataFrame(rows).reindex(columns=BO_COLUMNS), candidate_maps


def _select_objective(fitted: set[tuple[str, str, str]], process_type: str, material: str) -> str | None:
    targets = CUTTING_TARGETS if process_type == "cutting" else MILLING_TARGETS
    return next((target for target in targets if (process_type, material, target) in fitted), None)


def _observed_bounds(group: pd.DataFrame, process_type: str) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name in PROCESS_NUMERIC_FEATURES.get(process_type, PROCESS_NUMERIC_FEATURES["milling"]):
        if name not in group:
            continue
        values = pd.to_numeric(group[name], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if not values.empty:
            result[name] = [float(values.min()), float(values.max())]
    return result


def _samples(
    group: pd.DataFrame,
    process_type: str,
    material: str,
    target: str,
    bounds: dict[str, list[float]],
) -> list[BOSample]:
    samples: list[BOSample] = []
    for index, row in group.iterrows():
        target_value = _number(row.get(target))
        parameters = {name: value for name in bounds if (value := _number(row.get(name))) is not None}
        if target_value is None or len(parameters) != len(bounds):
            continue
        samples.append(
            BOSample(
                sample_id=f"offline-{process_type}-{material}-{index}",
                x_parameters=parameters,
                y_metrics={target: target_value},
                material=material,
                process_type=process_type,
                equipment_profile_id="offline-observed-scope",
                target_metric=target,
            )
        )
    return samples


def _legacy_row(
    response: dict[str, Any],
    parameters: dict[str, Any],
    process_type: str,
    material: str,
    target: str,
    rank: int,
) -> dict[str, Any]:
    prediction = response.get("predictions") or {}
    mean, uncertainty = prediction.get("mean"), prediction.get("uncertainty")
    row: dict[str, Any] = {column: np.nan for column in BO_COLUMNS}
    row.update(parameters)
    row.update(
        process_type=process_type,
        material=material,
        rank=rank,
        recommendation_type=(response.get("acquisition") or {}).get("type"),
        objective_value=mean,
        acquisition_score=(response.get("acquisition") or {}).get("score"),
        roughness_model_available=target in {"Sa_um", "cut_edge_Sa_um"},
        note="; ".join(response.get("warnings") or []),
    )
    prediction_columns = {
        "depth_um": ("predicted_depth_um", "predicted_depth_std_um"),
        "Sa_um": ("predicted_Sa_um", "predicted_Sa_std_um"),
        "cut_through": ("predicted_cut_through", "predicted_cut_through_std"),
        "kerf_top_width_um": ("predicted_kerf_top_width_um", None),
        "kerf_taper_deg": ("predicted_kerf_taper_deg", None),
        "cut_edge_Sa_um": ("predicted_cut_edge_Sa_um", None),
        "chipping_um": ("predicted_chipping_um", None),
    }
    mean_col, std_col = prediction_columns[target]
    row[mean_col] = mean
    if std_col:
        row[std_col] = uncertainty
    return row


def _truthy_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: str(value).strip().lower() in {"1", "true", "yes", "y"} if isinstance(value, str) else bool(value))


def _number(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
