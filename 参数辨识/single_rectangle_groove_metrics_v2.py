#!/usr/bin/env python
"""
Single-rectangle groove metrics from Keyence height CSV files.

This script is for files containing one rectangular groove. It avoids using
ragged connected-component contours as the measurement reference. Instead it:
  1. levels the upper surface;
  2. creates an unannotated depth image for locating the machined rectangle;
  3. detects the expected rectangular groove using a perimeter-edge template
     after row/column stripe suppression;
  4. refits each edge from local image-gradient maxima for QC;
  5. places a centered square ROI inside the fitted rectangle;
  6. reports mean depth and areal roughness metrics.

The default expected groove size is 200 um and can be changed with
--groove-size-um. In the default image-recognition mode, the final machining
rectangle is locked to this configured size after template localization; local
edge fitting is retained as QC. Use --use-edge-refined-rectangle only when the
actual edge fit, rather than the configured machining size, should define the
ROI center. The measurement ROI defaults to 100 um and is independently
controlled by --roi-side-um.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from scipy import ndimage, signal


ENCODINGS = ("utf-8-sig", "gb18030", "gbk", "cp932", "shift_jis", "latin1")
SUMMARY_COLUMNS = [
    "file",
    "status",
    "message",
    "detection_method",
    "rectangle_mode",
    "template_score",
    "second_template_score",
    "template_score_ratio",
    "xy_step_um",
    "field_width_um",
    "field_height_um",
    "plane_a",
    "plane_b",
    "plane_c",
    "plane_fit_points",
    "groove_size_um",
    "roi_side_um",
    "edge_left_x_um",
    "edge_right_x_um",
    "edge_top_y_um",
    "edge_bottom_y_um",
    "fitted_width_um",
    "fitted_height_um",
    "width_error_from_groove_size_um",
    "height_error_from_groove_size_um",
    "left_edge_rmse_um",
    "right_edge_rmse_um",
    "top_edge_rmse_um",
    "bottom_edge_rmse_um",
    "roi_center_x_um",
    "roi_center_y_um",
    "roi_area_um2",
    "roi_valid_points",
    "mean_depth_um",
    "Sa_um",
    "Sq_um",
    "Sz_um",
    "min_depth_um",
    "max_depth_um",
    "qa_overlay",
    "recognition_image",
]


@dataclass
class HeightMap:
    z_um: np.ndarray
    step_um: float
    metadata: dict[str, list[str]]
    source_encoding: str


@dataclass
class PlaneFit:
    a: float
    b: float
    c: float
    normal_scale: float
    n_points: int


@dataclass
class EdgeFit:
    kind: str
    side: str
    slope: float
    intercept: float
    rmse_um: float
    n_points: int

    def x_at_y(self, y_um: float) -> float:
        return self.slope * y_um + self.intercept

    def y_at_x(self, x_um: float) -> float:
        return self.slope * x_um + self.intercept


@dataclass
class RectangleFit:
    left: EdgeFit
    right: EdgeFit
    top: EdgeFit
    bottom: EdgeFit
    center_x_um: float
    center_y_um: float
    left_x_um: float
    right_x_um: float
    top_y_um: float
    bottom_y_um: float

    @property
    def width_um(self) -> float:
        return self.right_x_um - self.left_x_um

    @property
    def height_um(self) -> float:
        return self.bottom_y_um - self.top_y_um


def decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    best: tuple[int, str, str] | None = None
    keywords = ("XY", "水平", "垂直", "高度", "单位", "ImageDataCsv")
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        score = sum(text.count(k) for k in keywords) - text.count("\ufffd") * 10
        candidate = (score, enc, text)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        raise ValueError("Could not decode CSV with supported encodings.")
    return best[2], best[1]


def is_float_row(row: list[str]) -> bool:
    if len(row) < 8:
        return False
    try:
        for item in row:
            float(item)
    except ValueError:
        return False
    return True


def first_float(items: Iterable[str]) -> float | None:
    for item in items:
        try:
            return float(item)
        except ValueError:
            continue
    return None


def read_keyence_height_csv(path: Path) -> HeightMap:
    text, encoding = decode_csv_bytes(path.read_bytes())
    rows = list(csv.reader(text.splitlines()))

    data_start = None
    for idx, row in enumerate(rows):
        if len(row) == 1 and row[0].strip().lower() in {"高度", "height"}:
            data_start = idx + 1
            break
    if data_start is None:
        for idx, row in enumerate(rows):
            if is_float_row(row):
                data_start = idx
                break
    if data_start is None:
        raise ValueError("Could not locate numeric height matrix.")

    metadata = {row[0]: row[1:] for row in rows[:data_start] if row}
    numeric_rows = [row for row in rows[data_start:] if row]
    widths = {len(row) for row in numeric_rows}
    if len(widths) != 1:
        raise ValueError(f"Height matrix has inconsistent row lengths: {sorted(widths)}")
    z_um = np.array([[float(item) for item in row] for row in numeric_rows], dtype=float)

    expected_w = int(metadata.get("水平", [z_um.shape[1]])[0])
    expected_h = int(metadata.get("垂直", [z_um.shape[0]])[0])
    if z_um.shape != (expected_h, expected_w):
        raise ValueError(f"Matrix shape {z_um.shape} does not match metadata {(expected_h, expected_w)}.")

    xy_cal = metadata.get("XY校准") or metadata.get("XY calibration") or []
    xy_value = first_float(xy_cal)
    if xy_value is None:
        raise ValueError("Could not read XY calibration.")
    xy_unit = xy_cal[1].strip().lower() if len(xy_cal) > 1 else "um"
    if xy_unit in {"nm", "nanometer", "nanometers"}:
        step_um = xy_value / 1000.0
    elif xy_unit in {"um", "µm", "μm", "micrometer", "micrometers"}:
        step_um = xy_value
    else:
        raise ValueError(f"Unsupported XY calibration unit: {xy_unit!r}")

    return HeightMap(z_um=z_um, step_um=step_um, metadata=metadata, source_encoding=encoding)


def coordinate_grids(shape: tuple[int, int], step_um: float) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    x = np.arange(w, dtype=float) * step_um
    y = np.arange(h, dtype=float) * step_um
    return np.meshgrid(x, y)


def fit_plane_least_squares(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple[float, float, float]:
    design = np.column_stack((x, y, np.ones_like(x)))
    coeff, *_ = np.linalg.lstsq(design, z, rcond=None)
    return float(coeff[0]), float(coeff[1]), float(coeff[2])


def robust_fit_upper_surface(
    z_um: np.ndarray,
    step_um: float,
    top_percentile: float,
    trim_high_percentile: float,
    sigma: float,
    iterations: int,
    zero_is_invalid: bool,
) -> PlaneFit:
    x_grid, y_grid = coordinate_grids(z_um.shape, step_um)
    valid = np.isfinite(z_um)
    if zero_is_invalid:
        valid &= z_um != 0
    if valid.sum() < 100:
        raise ValueError("Too few valid points for plane fitting.")

    z_valid = z_um[valid]
    lower_gate = np.nanpercentile(z_valid, top_percentile)
    upper_gate = np.nanpercentile(z_valid, trim_high_percentile)
    fit_mask = valid & (z_um >= lower_gate) & (z_um <= upper_gate)

    for _ in range(iterations):
        if fit_mask.sum() < 100:
            raise ValueError("Upper-surface candidate mask became too small.")
        a, b, c = fit_plane_least_squares(x_grid[fit_mask], y_grid[fit_mask], z_um[fit_mask])
        residual = z_um - (a * x_grid + b * y_grid + c)
        r = residual[fit_mask]
        med = float(np.nanmedian(r))
        mad = float(np.nanmedian(np.abs(r - med)))
        robust_sigma = 1.4826 * mad if mad > 0 else float(np.nanstd(r))
        if not math.isfinite(robust_sigma) or robust_sigma == 0:
            break
        fit_mask = valid & (np.abs(residual - med) <= sigma * robust_sigma) & (z_um <= upper_gate)

    a, b, c = fit_plane_least_squares(x_grid[fit_mask], y_grid[fit_mask], z_um[fit_mask])
    return PlaneFit(a=a, b=b, c=c, normal_scale=math.sqrt(a * a + b * b + 1.0), n_points=int(fit_mask.sum()))


def level_to_plane(z_um: np.ndarray, step_um: float, plane: PlaneFit) -> np.ndarray:
    x_grid, y_grid = coordinate_grids(z_um.shape, step_um)
    return (z_um - (plane.a * x_grid + plane.b * y_grid + plane.c)) / plane.normal_scale


def select_two_edge_peaks(profile: np.ndarray, step_um: float, min_separation_um: float) -> tuple[int, int]:
    distance_px = max(5, int(round(min_separation_um / step_um)))
    prominence = max(float(np.nanstd(profile) * 0.20), 1e-9)
    peaks, props = signal.find_peaks(profile, distance=distance_px, prominence=prominence)
    if peaks.size < 2:
        peaks = np.argsort(profile)[-8:]
    ranked = sorted([(float(profile[idx]), int(idx)) for idx in peaks], reverse=True)
    best_pair: tuple[int, int] | None = None
    best_score = -np.inf
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            a = ranked[i][1]
            b = ranked[j][1]
            sep_um = abs(a - b) * step_um
            if sep_um < min_separation_um:
                continue
            score = ranked[i][0] + ranked[j][0]
            if score > best_score:
                best_score = score
                best_pair = (min(a, b), max(a, b))
    if best_pair is None:
        raise ValueError("Could not find two separated edge peaks.")
    return best_pair


def robust_line_fit(independent_um: np.ndarray, dependent_um: np.ndarray) -> tuple[float, float, float, int]:
    if independent_um.size < 5:
        raise ValueError("Too few edge points for line fitting.")
    mask = np.isfinite(independent_um) & np.isfinite(dependent_um)
    x = independent_um[mask]
    y = dependent_um[mask]
    for _ in range(4):
        if x.size < 5:
            break
        slope, intercept = np.polyfit(x, y, 1)
        residual = y - (slope * x + intercept)
        med = float(np.nanmedian(residual))
        mad = float(np.nanmedian(np.abs(residual - med)))
        sigma = 1.4826 * mad if mad > 0 else float(np.nanstd(residual))
        if not math.isfinite(sigma) or sigma == 0:
            break
        keep = np.abs(residual - med) <= 3.0 * sigma
        if keep.sum() == x.size:
            break
        x = x[keep]
        y = y[keep]
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    rmse = float(np.sqrt(np.nanmean(residual * residual)))
    return float(slope), float(intercept), rmse, int(x.size)


def fit_vertical_edge(
    gx_abs: np.ndarray,
    x0_idx: int,
    y_range: tuple[int, int],
    search_radius_px: int,
    step_um: float,
    side: str,
) -> EdgeFit:
    y0, y1 = y_range
    xs: list[float] = []
    ys: list[float] = []
    width = gx_abs.shape[1]
    for row in range(max(0, y0), min(gx_abs.shape[0], y1 + 1)):
        lo = max(0, x0_idx - search_radius_px)
        hi = min(width, x0_idx + search_radius_px + 1)
        segment = gx_abs[row, lo:hi]
        if segment.size == 0:
            continue
        local = int(np.argmax(segment)) + lo
        xs.append(local * step_um)
        ys.append(row * step_um)
    slope, intercept, rmse, n_points = robust_line_fit(np.asarray(ys), np.asarray(xs))
    return EdgeFit(kind="vertical", side=side, slope=slope, intercept=intercept, rmse_um=rmse, n_points=n_points)


def fit_horizontal_edge(
    gy_abs: np.ndarray,
    y0_idx: int,
    x_range: tuple[int, int],
    search_radius_px: int,
    step_um: float,
    side: str,
) -> EdgeFit:
    x0, x1 = x_range
    xs: list[float] = []
    ys: list[float] = []
    height = gy_abs.shape[0]
    for col in range(max(0, x0), min(gy_abs.shape[1], x1 + 1)):
        lo = max(0, y0_idx - search_radius_px)
        hi = min(height, y0_idx + search_radius_px + 1)
        segment = gy_abs[lo:hi, col]
        if segment.size == 0:
            continue
        local = int(np.argmax(segment)) + lo
        xs.append(col * step_um)
        ys.append(local * step_um)
    slope, intercept, rmse, n_points = robust_line_fit(np.asarray(xs), np.asarray(ys))
    return EdgeFit(kind="horizontal", side=side, slope=slope, intercept=intercept, rmse_um=rmse, n_points=n_points)


def fit_rectangle_edges(
    leveled_um: np.ndarray,
    step_um: float,
    min_edge_separation_um: float,
    edge_search_radius_um: float,
    smooth_sigma_px: float,
) -> RectangleFit:
    depth = -leveled_um
    smooth = ndimage.gaussian_filter(depth, sigma=smooth_sigma_px)
    gy, gx = np.gradient(smooth, step_um, step_um)
    gx_abs = np.abs(gx)
    gy_abs = np.abs(gy)
    x_profile = ndimage.gaussian_filter1d(np.nanmean(gx_abs, axis=0), sigma=8)
    y_profile = ndimage.gaussian_filter1d(np.nanmean(gy_abs, axis=1), sigma=8)

    left_idx, right_idx = select_two_edge_peaks(x_profile, step_um, min_edge_separation_um)
    top_idx, bottom_idx = select_two_edge_peaks(y_profile, step_um, min_edge_separation_um)

    pad = max(3, int(round(20.0 / step_um)))
    search_radius = max(3, int(round(edge_search_radius_um / step_um)))
    left = fit_vertical_edge(gx_abs, left_idx, (top_idx + pad, bottom_idx - pad), search_radius, step_um, "left")
    right = fit_vertical_edge(gx_abs, right_idx, (top_idx + pad, bottom_idx - pad), search_radius, step_um, "right")
    top = fit_horizontal_edge(gy_abs, top_idx, (left_idx + pad, right_idx - pad), search_radius, step_um, "top")
    bottom = fit_horizontal_edge(gy_abs, bottom_idx, (left_idx + pad, right_idx - pad), search_radius, step_um, "bottom")

    # Iterate once at the fitted midpoint to report consistent edge positions.
    center_y = ((top_idx + bottom_idx) / 2.0) * step_um
    center_x = ((left_idx + right_idx) / 2.0) * step_um
    left_x = left.x_at_y(center_y)
    right_x = right.x_at_y(center_y)
    top_y = top.y_at_x(center_x)
    bottom_y = bottom.y_at_x(center_x)
    center_x = (left_x + right_x) / 2.0
    center_y = (top_y + bottom_y) / 2.0
    left_x = left.x_at_y(center_y)
    right_x = right.x_at_y(center_y)
    top_y = top.y_at_x(center_x)
    bottom_y = bottom.y_at_x(center_x)
    center_x = (left_x + right_x) / 2.0
    center_y = (top_y + bottom_y) / 2.0

    return RectangleFit(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        center_x_um=float(center_x),
        center_y_um=float(center_y),
        left_x_um=float(left_x),
        right_x_um=float(right_x),
        top_y_um=float(top_y),
        bottom_y_um=float(bottom_y),
    )




def robust_normalize01(image: np.ndarray, low_percentile: float = 1.0, high_percentile: float = 99.0) -> np.ndarray:
    valid = np.isfinite(image)
    if valid.sum() < 100:
        raise ValueError("Too few valid points for robust normalization.")
    lo, hi = np.nanpercentile(image[valid], [low_percentile, high_percentile])
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        raise ValueError("Image has insufficient contrast for robust normalization.")
    out = np.clip((image - lo) / (hi - lo), 0.0, 1.0)
    fill = float(np.nanmedian(out[valid]))
    return np.where(valid, out, fill).astype(float)


def remove_scan_stripes(
    depth_um: np.ndarray,
    row_sigma_px: float,
    col_sigma_px: float,
    col_weight: float,
) -> np.ndarray:
    """Suppress long horizontal/vertical scan-band bias without using morphology.

    Keyence height maps in this dataset contain row-wise bands whose contrast can be
    stronger than the actual groove boundary.  A filled-square template therefore
    tends to lock onto bright bands.  This function estimates the one-dimensional
    row and column bias from medians and subtracts only the high-frequency part of
    that bias, preserving the slow field-scale trend for the preceding plane fit.
    """
    valid = np.isfinite(depth_um)
    if valid.sum() < 100:
        raise ValueError("Too few valid points for stripe correction.")
    fill = float(np.nanmedian(depth_um[valid]))
    corrected = np.where(valid, depth_um, fill).astype(float)

    if row_sigma_px > 0:
        row_median = np.nanmedian(corrected, axis=1)
        row_smooth = ndimage.gaussian_filter1d(row_median, sigma=row_sigma_px, mode="nearest")
        corrected = corrected - (row_median - row_smooth)[:, None]

    if col_sigma_px > 0 and col_weight != 0:
        col_median = np.nanmedian(corrected, axis=0)
        col_smooth = ndimage.gaussian_filter1d(col_median, sigma=col_sigma_px, mode="nearest")
        corrected = corrected - col_weight * (col_median - col_smooth)[None, :]

    return np.where(valid, corrected, np.nan)


def normalize_depth_for_perimeter_recognition(
    leveled_um: np.ndarray,
    row_sigma_px: float,
    col_sigma_px: float,
    col_weight: float,
) -> np.ndarray:
    depth = -leveled_um
    corrected = remove_scan_stripes(depth, row_sigma_px, col_sigma_px, col_weight)
    return robust_normalize01(corrected, 1.0, 99.0)


def shifted_score_components(
    v_line_mean: np.ndarray,
    h_line_mean: np.ndarray,
    half_px: int,
) -> tuple[np.ndarray, tuple[slice, slice]]:
    h, w = v_line_mean.shape
    if 2 * half_px + 1 >= min(h, w):
        raise ValueError("Perimeter template is too large for the image field.")
    row_slice = slice(half_px, h - half_px)
    col_slice = slice(half_px, w - half_px)
    left = v_line_mean[row_slice, slice(0, w - 2 * half_px)]
    right = v_line_mean[row_slice, slice(2 * half_px, w)]
    top = h_line_mean[slice(0, h - 2 * half_px), col_slice]
    bottom = h_line_mean[slice(2 * half_px, h), col_slice]
    components = np.stack([left, right, top, bottom], axis=0)
    return components, (row_slice, col_slice)


def locate_perimeter_template(
    recognition_image: np.ndarray,
    valid: np.ndarray,
    step_um: float,
    groove_size_um: float,
    edge_bias_subtract: float,
    exclusion_radius_um: float,
) -> tuple[float, float, int, float, float, float]:
    """Locate a nominal square by matching its four-edge perimeter.

    The score is not the mean depth inside a square.  It is a constrained four-side
    edge score, so isolated horizontal bands or a single bright wall cannot dominate
    unless the other sides are also supported.
    """
    target_px = max(5, int(round(groove_size_um / step_um)))
    half_px = max(2, target_px // 2)
    if 2 * half_px + 1 >= min(recognition_image.shape):
        raise ValueError(
            f"Configured groove size {groove_size_um:g} um is too large for image field "
            f"{recognition_image.shape} at {step_um:g} um/px."
        )

    gy, gx = np.gradient(recognition_image, step_um, step_um)
    gx_abs = robust_normalize01(np.abs(gx), 1.0, 99.0)
    gy_abs = robust_normalize01(np.abs(gy), 1.0, 99.0)

    # Suppress globally repeated scan-line edges.  The subtraction is deliberately
    # partial: real rectangle edges are local in the orthogonal direction and remain.
    if edge_bias_subtract > 0:
        gx_abs = np.clip(gx_abs - edge_bias_subtract * np.nanmedian(gx_abs, axis=0, keepdims=True), 0.0, None)
        gy_abs = np.clip(gy_abs - edge_bias_subtract * np.nanmedian(gy_abs, axis=1, keepdims=True), 0.0, None)

    v_line_mean = ndimage.uniform_filter(gx_abs, size=(target_px, 1), mode="constant", cval=0.0)
    h_line_mean = ndimage.uniform_filter(gy_abs, size=(1, target_px), mode="constant", cval=0.0)
    components, (row_slice, col_slice) = shifted_score_components(v_line_mean, h_line_mean, half_px)

    arithmetic = np.nanmean(components, axis=0)
    harmonic = 4.0 / np.nansum(1.0 / (components + 1e-3), axis=0)
    weakest_side = np.nanmin(components, axis=0)
    local_score = 0.50 * arithmetic + 0.30 * harmonic + 0.20 * weakest_side

    score = np.full(recognition_image.shape, -np.inf, dtype=float)
    score[row_slice, col_slice] = local_score

    # Reject centers whose nominal rectangle would include many invalid points.
    valid_mean = ndimage.uniform_filter(valid.astype(float), size=(target_px, target_px), mode="constant", cval=0.0)
    score[valid_mean < 0.90] = -np.inf

    if not np.isfinite(score).any():
        raise ValueError("Perimeter template search could not find a valid rectangular groove candidate.")

    center_row, center_col = np.unravel_index(int(np.nanargmax(score)), score.shape)
    best_score = float(score[center_row, center_col])

    score_second = score.copy()
    exclusion_px = max(1, int(round(exclusion_radius_um / step_um)))
    r0 = max(0, center_row - exclusion_px)
    r1 = min(score.shape[0], center_row + exclusion_px + 1)
    c0 = max(0, center_col - exclusion_px)
    c1 = min(score.shape[1], center_col + exclusion_px + 1)
    score_second[r0:r1, c0:c1] = -np.inf
    second_score = float(np.nanmax(score_second)) if np.isfinite(score_second).any() else float("nan")
    score_ratio = best_score / second_score if math.isfinite(second_score) and second_score > 0 else float("nan")

    return float(center_col * step_um), float(center_row * step_um), target_px, best_score, second_score, score_ratio


def fit_rectangle_edges_from_perimeter_image(
    leveled_um: np.ndarray,
    step_um: float,
    groove_size_um: float,
    edge_search_radius_um: float,
    smooth_sigma_px: float,
    row_sigma_px: float,
    col_sigma_px: float,
    col_weight: float,
    edge_bias_subtract: float,
    lock_groove_size: bool,
) -> tuple[RectangleFit, np.ndarray, float, float, float]:
    valid = np.isfinite(leveled_um)
    recognition_image = normalize_depth_for_perimeter_recognition(
        leveled_um,
        row_sigma_px=row_sigma_px,
        col_sigma_px=col_sigma_px,
        col_weight=col_weight,
    )
    smooth = ndimage.gaussian_filter(recognition_image, sigma=smooth_sigma_px)
    center_x_um, center_y_um, target_px, score, second_score, score_ratio = locate_perimeter_template(
        smooth,
        valid,
        step_um,
        groove_size_um,
        edge_bias_subtract=edge_bias_subtract,
        exclusion_radius_um=max(120.0, groove_size_um * 0.60),
    )

    gy, gx = np.gradient(smooth, step_um, step_um)
    gx_abs = np.abs(gx)
    gy_abs = np.abs(gy)

    center_col = int(round(center_x_um / step_um))
    center_row = int(round(center_y_um / step_um))
    half_px = target_px / 2.0
    left_idx = int(round(center_col - half_px))
    right_idx = int(round(center_col + half_px))
    top_idx = int(round(center_row - half_px))
    bottom_idx = int(round(center_row + half_px))

    search_radius = max(3, int(round(edge_search_radius_um / step_um)))
    trim_px = max(3, int(round(min(25.0, groove_size_um * 0.12) / step_um)))
    left = fit_vertical_edge(gx_abs, left_idx, (top_idx + trim_px, bottom_idx - trim_px), search_radius, step_um, "left")
    right = fit_vertical_edge(gx_abs, right_idx, (top_idx + trim_px, bottom_idx - trim_px), search_radius, step_um, "right")
    top = fit_horizontal_edge(gy_abs, top_idx, (left_idx + trim_px, right_idx - trim_px), search_radius, step_um, "top")
    bottom = fit_horizontal_edge(gy_abs, bottom_idx, (left_idx + trim_px, right_idx - trim_px), search_radius, step_um, "bottom")

    if lock_groove_size:
        center_x = center_x_um
        center_y = center_y_um
        left_x = center_x - groove_size_um / 2.0
        right_x = center_x + groove_size_um / 2.0
        top_y = center_y - groove_size_um / 2.0
        bottom_y = center_y + groove_size_um / 2.0
    else:
        center_y = center_y_um
        center_x = center_x_um
        left_x = left.x_at_y(center_y)
        right_x = right.x_at_y(center_y)
        top_y = top.y_at_x(center_x)
        bottom_y = bottom.y_at_x(center_x)
        center_x = (left_x + right_x) / 2.0
        center_y = (top_y + bottom_y) / 2.0
        left_x = left.x_at_y(center_y)
        right_x = right.x_at_y(center_y)
        top_y = top.y_at_x(center_x)
        bottom_y = bottom.y_at_x(center_x)
        center_x = (left_x + right_x) / 2.0
        center_y = (top_y + bottom_y) / 2.0

    rect = RectangleFit(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        center_x_um=float(center_x),
        center_y_um=float(center_y),
        left_x_um=float(left_x),
        right_x_um=float(right_x),
        top_y_um=float(top_y),
        bottom_y_um=float(bottom_y),
    )
    return rect, recognition_image, score, second_score, score_ratio


def normalize_depth_for_recognition(leveled_um: np.ndarray) -> np.ndarray:
    depth = -leveled_um
    valid = np.isfinite(depth)
    if valid.sum() < 100:
        raise ValueError("Too few valid points for image recognition.")
    lo, hi = np.nanpercentile(depth[valid], [2.0, 98.0])
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        raise ValueError("Depth image has insufficient contrast for image recognition.")
    image = np.clip((depth - lo) / (hi - lo), 0.0, 1.0)
    fill = float(np.nanmedian(image[valid]))
    image = np.where(valid, image, fill)
    return image.astype(float)


def centered_box_mean(image: np.ndarray, valid: np.ndarray, height_px: int, width_px: int) -> tuple[np.ndarray, np.ndarray]:
    area = float(height_px * width_px)
    image_sum = ndimage.uniform_filter(image * valid, size=(height_px, width_px), mode="constant", cval=0.0) * area
    valid_count = ndimage.uniform_filter(valid.astype(float), size=(height_px, width_px), mode="constant", cval=0.0) * area
    mean = np.full(image.shape, np.nan, dtype=float)
    np.divide(image_sum, valid_count, out=mean, where=valid_count > 0)
    return mean, valid_count


def locate_square_template(
    recognition_image: np.ndarray,
    valid: np.ndarray,
    step_um: float,
    groove_size_um: float,
    ring_margin_um: float,
) -> tuple[float, float, int, int, float]:
    target_px = max(5, int(round(groove_size_um / step_um)))
    if target_px >= min(recognition_image.shape):
        raise ValueError(
            f"Configured groove size {groove_size_um:g} um is too large for image field "
            f"{recognition_image.shape} at {step_um:g} um/px."
        )

    margin_px = max(6, int(round(ring_margin_um / step_um)))
    outer_px = target_px + 2 * margin_px
    if outer_px >= min(recognition_image.shape):
        outer_px = target_px + 2 * max(3, int(round(10.0 / step_um)))

    inner_mean, inner_count = centered_box_mean(recognition_image, valid, target_px, target_px)
    outer_mean, outer_count = centered_box_mean(recognition_image, valid, outer_px, outer_px)
    inner_sum = inner_mean * inner_count
    outer_sum = outer_mean * outer_count
    ring_count = outer_count - inner_count
    ring_sum = outer_sum - inner_sum
    ring_mean = np.full(recognition_image.shape, np.nan, dtype=float)
    np.divide(ring_sum, ring_count, out=ring_mean, where=ring_count > 0)

    score = inner_mean - ring_mean
    min_inner_count = 0.90 * target_px * target_px
    min_ring_count = 0.70 * max(1, outer_px * outer_px - target_px * target_px)
    score[(inner_count < min_inner_count) | (ring_count < min_ring_count)] = -np.inf

    half = target_px / 2.0
    outer_half = outer_px / 2.0
    h, w = recognition_image.shape
    yy, xx = np.indices(recognition_image.shape)
    inside_field = (xx >= outer_half) & (xx <= (w - 1 - outer_half)) & (yy >= outer_half) & (yy <= (h - 1 - outer_half))
    score[~inside_field] = -np.inf

    if not np.isfinite(score).any():
        raise ValueError("Image template search could not find a valid rectangular groove candidate.")
    center_row, center_col = np.unravel_index(int(np.nanargmax(score)), score.shape)
    center_x_um = float(center_col * step_um)
    center_y_um = float(center_row * step_um)
    return center_x_um, center_y_um, target_px, outer_px, float(score[center_row, center_col])


def fit_rectangle_edges_from_image(
    leveled_um: np.ndarray,
    step_um: float,
    groove_size_um: float,
    edge_search_radius_um: float,
    smooth_sigma_px: float,
    ring_margin_um: float,
    lock_groove_size: bool,
) -> tuple[RectangleFit, np.ndarray, float]:
    valid = np.isfinite(leveled_um)
    recognition_image = normalize_depth_for_recognition(leveled_um)
    smooth = ndimage.gaussian_filter(recognition_image, sigma=smooth_sigma_px)
    center_x_um, center_y_um, target_px, _outer_px, score = locate_square_template(
        smooth,
        valid,
        step_um,
        groove_size_um,
        ring_margin_um,
    )

    gy, gx = np.gradient(smooth, step_um, step_um)
    gx_abs = np.abs(gx)
    gy_abs = np.abs(gy)

    center_col = int(round(center_x_um / step_um))
    center_row = int(round(center_y_um / step_um))
    half_px = target_px / 2.0
    left_idx = int(round(center_col - half_px))
    right_idx = int(round(center_col + half_px))
    top_idx = int(round(center_row - half_px))
    bottom_idx = int(round(center_row + half_px))

    search_radius = max(3, int(round(edge_search_radius_um / step_um)))
    trim_px = max(3, int(round(min(25.0, groove_size_um * 0.12) / step_um)))
    left = fit_vertical_edge(gx_abs, left_idx, (top_idx + trim_px, bottom_idx - trim_px), search_radius, step_um, "left")
    right = fit_vertical_edge(gx_abs, right_idx, (top_idx + trim_px, bottom_idx - trim_px), search_radius, step_um, "right")
    top = fit_horizontal_edge(gy_abs, top_idx, (left_idx + trim_px, right_idx - trim_px), search_radius, step_um, "top")
    bottom = fit_horizontal_edge(gy_abs, bottom_idx, (left_idx + trim_px, right_idx - trim_px), search_radius, step_um, "bottom")

    if lock_groove_size:
        center_x = center_x_um
        center_y = center_y_um
        left_x = center_x - groove_size_um / 2.0
        right_x = center_x + groove_size_um / 2.0
        top_y = center_y - groove_size_um / 2.0
        bottom_y = center_y + groove_size_um / 2.0
    else:
        center_y = center_y_um
        center_x = center_x_um
        left_x = left.x_at_y(center_y)
        right_x = right.x_at_y(center_y)
        top_y = top.y_at_x(center_x)
        bottom_y = bottom.y_at_x(center_x)
        center_x = (left_x + right_x) / 2.0
        center_y = (top_y + bottom_y) / 2.0
        left_x = left.x_at_y(center_y)
        right_x = right.x_at_y(center_y)
        top_y = top.y_at_x(center_x)
        bottom_y = bottom.y_at_x(center_x)
        center_x = (left_x + right_x) / 2.0
        center_y = (top_y + bottom_y) / 2.0

    rect = RectangleFit(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        center_x_um=float(center_x),
        center_y_um=float(center_y),
        left_x_um=float(left_x),
        right_x_um=float(right_x),
        top_y_um=float(top_y),
        bottom_y_um=float(bottom_y),
    )
    return rect, recognition_image, score


def square_roi_mask(shape: tuple[int, int], step_um: float, center_x_um: float, center_y_um: float, side_um: float) -> np.ndarray:
    x_grid, y_grid = coordinate_grids(shape, step_um)
    half = side_um / 2.0
    return (np.abs(x_grid - center_x_um) <= half) & (np.abs(y_grid - center_y_um) <= half)


def compute_roi_metrics(leveled_um: np.ndarray, roi_mask: np.ndarray) -> dict[str, float]:
    values = leveled_um[roi_mask & np.isfinite(leveled_um)]
    if values.size == 0:
        raise ValueError("ROI contains no valid height values.")
    depth = -values
    mean_height = float(np.mean(values))
    centered = values - mean_height
    return {
        "roi_valid_points": int(values.size),
        "mean_depth_um": float(np.mean(depth)),
        "Sa_um": float(np.mean(np.abs(centered))),
        "Sq_um": float(np.sqrt(np.mean(centered * centered))),
        "Sz_um": float(np.max(values) - np.min(values)),
        "min_depth_um": float(np.min(depth)),
        "max_depth_um": float(np.max(depth)),
    }


def safe_output_name(path: Path) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", path.stem, flags=re.UNICODE)
    return stem.strip("._") or "csv"


def save_qa_overlay(
    output_png: Path,
    leveled_um: np.ndarray,
    rect: RectangleFit,
    roi_side_um: float,
    groove_size_um: float | None,
    title: str,
    step_um: float,
) -> None:
    depth = -leveled_um
    h, w = depth.shape
    extent = [0, (w - 1) * step_um, (h - 1) * step_um, 0]
    fig, ax = plt.subplots(figsize=(10, 7), dpi=160)
    image = ax.imshow(depth, cmap="viridis", extent=extent)

    # Fitted rectangle, reported at the fitted center.
    ax.add_patch(
        Rectangle(
            (rect.left_x_um, rect.top_y_um),
            rect.width_um,
            rect.height_um,
            fill=False,
            edgecolor="white",
            linewidth=1.2,
            linestyle="--",
        )
    )
    ax.add_patch(
        Rectangle(
            (rect.center_x_um - roi_side_um / 2.0, rect.center_y_um - roi_side_um / 2.0),
            roi_side_um,
            roi_side_um,
            fill=False,
            edgecolor="red",
            linewidth=1.4,
        )
    )
    if groove_size_um is not None:
        ax.add_patch(
            Rectangle(
                (rect.center_x_um - groove_size_um / 2.0, rect.center_y_um - groove_size_um / 2.0),
                groove_size_um,
                groove_size_um,
                fill=False,
                edgecolor="orange",
                linewidth=0.9,
                linestyle=":",
            )
        )
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.set_title(title)
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("depth after leveling (um)")
    fig.tight_layout()
    fig.savefig(output_png)
    plt.close(fig)


def save_recognition_image(output_png: Path, recognition_image: np.ndarray) -> None:
    fig, ax = plt.subplots(figsize=(10, 7), dpi=160)
    ax.imshow(recognition_image, cmap="gray", vmin=0.0, vmax=1.0)
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.savefig(output_png, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def analyze_file(path: Path, args: argparse.Namespace, output_dir: Path) -> dict[str, object]:
    hm = read_keyence_height_csv(path)
    plane = robust_fit_upper_surface(
        hm.z_um,
        hm.step_um,
        args.top_percentile,
        args.trim_high_percentile,
        args.plane_sigma,
        args.plane_iterations,
        args.zero_is_invalid,
    )
    leveled = level_to_plane(hm.z_um, hm.step_um, plane)
    file_output_dir = output_dir / safe_output_name(path)
    file_output_dir.mkdir(parents=True, exist_ok=True)
    recognition_path = file_output_dir / "recognition_image.png"
    detection_score: float | None = None
    second_detection_score: float | None = None
    detection_score_ratio: float | None = None
    if args.detection_method == "perimeter":
        rect, recognition_image, detection_score, second_detection_score, detection_score_ratio = fit_rectangle_edges_from_perimeter_image(
            leveled,
            hm.step_um,
            args.groove_size_um,
            args.edge_search_radius_um,
            args.smooth_sigma_px,
            args.stripe_row_sigma_px,
            args.stripe_col_sigma_px,
            args.stripe_col_weight,
            args.edge_bias_subtract,
            not args.use_edge_refined_rectangle,
        )
        save_recognition_image(recognition_path, recognition_image)
    elif args.detection_method == "image":
        rect, recognition_image, detection_score = fit_rectangle_edges_from_image(
            leveled,
            hm.step_um,
            args.groove_size_um,
            args.edge_search_radius_um,
            args.smooth_sigma_px,
            args.template_ring_margin_um,
            not args.use_edge_refined_rectangle,
        )
        save_recognition_image(recognition_path, recognition_image)
    else:
        rect = fit_rectangle_edges(
            leveled,
            hm.step_um,
            args.min_edge_separation_um,
            args.edge_search_radius_um,
            args.smooth_sigma_px,
        )
        recognition_path = Path("")

    roi_mask = square_roi_mask(leveled.shape, hm.step_um, rect.center_x_um, rect.center_y_um, args.roi_side_um)
    metrics = compute_roi_metrics(leveled, roi_mask)

    qa_path = file_output_dir / "qa_overlay.png"
    ascii_name = path.name.encode("ascii", errors="ignore").decode("ascii").strip() or "height_csv"
    save_qa_overlay(qa_path, leveled, rect, args.roi_side_um, args.groove_size_um, ascii_name, hm.step_um)

    width_error = rect.width_um - args.groove_size_um if args.groove_size_um is not None else ""
    height_error = rect.height_um - args.groove_size_um if args.groove_size_um is not None else ""
    if args.detection_method == "profile":
        rectangle_mode = "profile_edges"
    else:
        rectangle_mode = "edge_refined" if args.use_edge_refined_rectangle else "fixed_template"

    row: dict[str, object] = {column: "" for column in SUMMARY_COLUMNS}
    row.update(
        {
            "file": path.name,
            "status": "ok",
            "message": (
                f"detection_method={args.detection_method}; rectangle_mode={rectangle_mode}; "
                f"template_score={detection_score:.6g}; "
                f"second_template_score={second_detection_score:.6g}; "
                f"template_score_ratio={detection_score_ratio:.6g}"
            )
            if detection_score is not None and second_detection_score is not None
            else (
                f"detection_method={args.detection_method}; rectangle_mode={rectangle_mode}; template_score={detection_score:.6g}"
                if detection_score is not None
                else f"detection_method={args.detection_method}"
            ),
            "detection_method": args.detection_method,
            "rectangle_mode": rectangle_mode,
            "template_score": detection_score if detection_score is not None else "",
            "second_template_score": second_detection_score if second_detection_score is not None else "",
            "template_score_ratio": detection_score_ratio if detection_score_ratio is not None else "",
            "xy_step_um": hm.step_um,
            "field_width_um": float((hm.z_um.shape[1] - 1) * hm.step_um),
            "field_height_um": float((hm.z_um.shape[0] - 1) * hm.step_um),
            "plane_a": plane.a,
            "plane_b": plane.b,
            "plane_c": plane.c,
            "plane_fit_points": plane.n_points,
            "groove_size_um": args.groove_size_um if args.groove_size_um is not None else "",
            "roi_side_um": args.roi_side_um,
            "edge_left_x_um": rect.left_x_um,
            "edge_right_x_um": rect.right_x_um,
            "edge_top_y_um": rect.top_y_um,
            "edge_bottom_y_um": rect.bottom_y_um,
            "fitted_width_um": rect.width_um,
            "fitted_height_um": rect.height_um,
            "width_error_from_groove_size_um": width_error,
            "height_error_from_groove_size_um": height_error,
            "left_edge_rmse_um": rect.left.rmse_um,
            "right_edge_rmse_um": rect.right.rmse_um,
            "top_edge_rmse_um": rect.top.rmse_um,
            "bottom_edge_rmse_um": rect.bottom.rmse_um,
            "roi_center_x_um": rect.center_x_um,
            "roi_center_y_um": rect.center_y_um,
            "roi_area_um2": float(roi_mask.sum() * hm.step_um * hm.step_um),
            "qa_overlay": str(qa_path),
            "recognition_image": str(recognition_path) if recognition_path else "",
        }
    )
    row.update(metrics)

    if args.save_arrays:
        np.save(file_output_dir / "leveled_height_um.npy", leveled)
        np.save(file_output_dir / "center_roi_mask.npy", roi_mask)

    (file_output_dir / "metrics.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def write_summary(summary_path: Path, rows: list[dict[str, object]]) -> None:
    with summary_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in SUMMARY_COLUMNS})


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Single rectangular groove metrics from Keyence height CSV files.")
    parser.add_argument("--input-dir", type=Path, default=script_dir)
    parser.add_argument("--pattern", default="*_高度.csv")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "single_rectangle_groove_metrics_results")
    parser.add_argument("--groove-size-um", type=float, default=200.0)
    parser.add_argument("--nominal-groove-size-um", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--roi-side-um", type=float, default=100.0)
    parser.add_argument("--detection-method", choices=("perimeter", "image", "profile"), default="perimeter")
    parser.add_argument("--template-ring-margin-um", type=float, default=40.0)
    parser.add_argument("--use-edge-refined-rectangle", action="store_true")
    parser.add_argument("--min-edge-separation-um", type=float, default=120.0)
    parser.add_argument("--edge-search-radius-um", type=float, default=20.0)
    parser.add_argument("--smooth-sigma-px", type=float, default=2.0)
    parser.add_argument("--stripe-row-sigma-px", type=float, default=25.0)
    parser.add_argument("--stripe-col-sigma-px", type=float, default=25.0)
    parser.add_argument("--stripe-col-weight", type=float, default=0.5)
    parser.add_argument("--edge-bias-subtract", type=float, default=0.5)
    parser.add_argument("--top-percentile", type=float, default=60.0)
    parser.add_argument("--trim-high-percentile", type=float, default=99.8)
    parser.add_argument("--plane-sigma", type=float, default=3.0)
    parser.add_argument("--plane-iterations", type=int, default=6)
    parser.add_argument("--zero-is-invalid", action="store_true")
    parser.add_argument("--save-arrays", action="store_true")
    parser.add_argument("csv_files", nargs="*", type=Path)
    args = parser.parse_args()
    if args.nominal_groove_size_um is not None:
        args.groove_size_um = args.nominal_groove_size_um

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.csv_files:
        csv_paths = [p if p.is_absolute() else Path.cwd() / p for p in args.csv_files]
    else:
        csv_paths = sorted(args.input_dir.glob(args.pattern), key=lambda p: p.name)
    csv_paths = [p for p in csv_paths if p.is_file()]
    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found in {args.input_dir} matching {args.pattern!r}.")

    rows: list[dict[str, object]] = []
    for index, path in enumerate(csv_paths, start=1):
        print(f"[{index}/{len(csv_paths)}] {path.name}")
        try:
            row = analyze_file(path, args, args.output_dir)
            rows.append(row)
            print("  ok")
        except Exception as exc:
            row = {column: "" for column in SUMMARY_COLUMNS}
            row.update({"file": path.name, "status": "error", "message": str(exc)})
            rows.append(row)
            print(f"  error: {exc}")

    summary_path = args.output_dir / "single_rectangle_groove_metrics_summary.csv"
    write_summary(summary_path, rows)
    print(f"Wrote summary: {summary_path}")
    print(f"Wrote per-file outputs under: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
