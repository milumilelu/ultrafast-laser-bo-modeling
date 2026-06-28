"""Data cleaning and schema unification for laser processing experiments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STANDARD_COLUMNS = [
    "material",
    "pulse_width_ps",
    "frequency_kHz",
    "hatch_spacing_um",
    "passes",
    "scan_speed_mm_s",
    "power_W",
    "depth_um",
    "Sa_um",
    "Sq_um",
    "Sz_um",
    "source_file",
    "valid_flag",
    "note",
]

NUMERIC_STANDARD_COLUMNS = [
    "pulse_width_ps",
    "frequency_kHz",
    "hatch_spacing_um",
    "passes",
    "scan_speed_mm_s",
    "power_W",
    "depth_um",
    "Sa_um",
    "Sq_um",
    "Sz_um",
]


def normalize_column_name(name: Any) -> str:
    """Normalize a raw column name for robust semantic matching."""
    text = "" if name is None else str(name)
    text = text.strip().lower()
    text = text.replace("μ", "u").replace("µ", "u")
    text = re.sub(r"\s+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("/", "_").replace("-", "_")
    return text


def _infer_standard_column(raw_name: Any, index: int | None = None) -> str | None:
    norm = normalize_column_name(raw_name)
    if norm.startswith("unnamed"):
        return None
    rules = [
        ("pulse_width_ps", ("脉宽", "脉冲宽度", "pulsewidth", "pulse_width")),
        ("frequency_kHz", ("频率", "重复频率", "frequency", "freq")),
        ("hatch_spacing_um", ("间距", "填充间距", "hatch", "spacing")),
        ("passes", ("重复加工次数", "加工次数", "passes", "pass")),
        ("scan_speed_mm_s", ("速度", "扫描速度", "scanspeed", "scan_speed", "speed")),
        ("power_W", ("功率", "power")),
        ("depth_um", ("mean_depth_um", "深度", "depth")),
        ("Sa_um", ("sa_um", "粗糙度", "sa")),
        ("Sq_um", ("sq_um", "sq")),
        ("Sz_um", ("sz_um", "sz")),
        ("note", ("备注", "note", "comment")),
    ]
    for standard, aliases in rules:
        if any(alias in norm for alias in aliases):
            return standard
    return None


def _unit_transform(raw_name: Any, standard: str, values: pd.Series) -> pd.Series:
    """Convert matched columns to the requested standard units."""
    norm = normalize_column_name(raw_name)
    numeric = pd.to_numeric(values, errors="coerce")
    if standard == "pulse_width_ps":
        if "fs" in norm or "飞秒" in norm or numeric.dropna().median() > 50:
            return numeric / 1000.0
    if standard == "hatch_spacing_um":
        if "mm" in norm or numeric.dropna().median() < 0.1:
            return numeric * 1000.0
    return numeric


def clean_material_table(
    df: pd.DataFrame,
    material: str,
    metadata: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Map a raw material table to the unified experiment schema."""
    raw_columns = list(df.columns)
    mapped: dict[str, pd.Series] = {}
    column_map: dict[str, str] = {}
    notes: list[str] = []

    for col in raw_columns:
        standard = _infer_standard_column(col)
        if standard is None:
            if not normalize_column_name(col).startswith("unnamed"):
                notes.append(f"ignored column: {col}")
            continue
        if standard == "note":
            mapped[standard] = df[col].astype("string")
        elif standard not in mapped:
            mapped[standard] = _unit_transform(col, standard, df[col])
        column_map[str(col)] = standard

    out = pd.DataFrame(index=df.index)
    out["material"] = material
    for col in NUMERIC_STANDARD_COLUMNS:
        out[col] = mapped.get(col, pd.Series(np.nan, index=df.index, dtype="float64"))
    out["source_file"] = metadata.get("source_file")

    row_notes = []
    existing_note = mapped.get("note")
    for idx in df.index:
        parts = []
        missing_process = [
            col
            for col in ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s"]
            if pd.isna(out.at[idx, col])
        ]
        if missing_process:
            parts.append("missing process fields: " + ",".join(missing_process))
        if pd.isna(out.at[idx, "depth_um"]) and pd.isna(out.at[idx, "Sa_um"]):
            parts.append("missing both depth_um and Sa_um")
        if existing_note is not None and idx in existing_note.index and pd.notna(existing_note.loc[idx]):
            parts.append(str(existing_note.loc[idx]))
        row_notes.append("; ".join(parts))
    out["note"] = row_notes

    required = ["pulse_width_ps", "frequency_kHz", "hatch_spacing_um", "passes", "scan_speed_mm_s"]
    out["valid_flag"] = out[required].notna().all(axis=1) & (out["depth_um"].notna() | out["Sa_um"].notna())
    out = out[STANDARD_COLUMNS]

    summary = {
        "material": material,
        "source_file": metadata.get("source_file"),
        "sheet_name": metadata.get("sheet_name"),
        "encoding": metadata.get("encoding"),
        "n_rows_raw": int(len(df)),
        "n_columns_raw": int(len(raw_columns)),
        "raw_columns": raw_columns,
        "column_map": column_map,
        "ignored_columns": [str(c) for c in raw_columns if str(c) not in column_map],
    }
    return out, summary


def combine_cleaned_tables(cleaned: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate cleaned tables while preserving the standard schema."""
    if not cleaned:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    combined = pd.concat(cleaned, ignore_index=True)
    return combined[STANDARD_COLUMNS]


def count_outlier_rows(df: pd.DataFrame, columns: list[str]) -> int:
    """Count rows with at least one IQR outlier among selected numeric columns."""
    mask = pd.Series(False, index=df.index)
    for col in columns:
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(values) < 4:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0 or pd.isna(iqr):
            continue
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask |= (df[col] < low) | (df[col] > high)
    return int(mask.sum())


def build_data_quality_report(unified: pd.DataFrame) -> pd.DataFrame:
    """Build per-material quality metrics for the unified experiment table."""
    rows = []
    for material, group in unified.groupby("material", dropna=False):
        numeric = group[NUMERIC_STANDARD_COLUMNS]
        rows.append(
            {
                "material": material,
                "n_samples": int(len(group)),
                "valid_rows": int(group["valid_flag"].sum()),
                "valid_depth_samples": int(group["depth_um"].notna().sum()),
                "valid_roughness_samples": int(group["Sa_um"].notna().sum()),
                "missing_field_ratio": float(numeric.isna().mean().mean()),
                "outlier_row_count": count_outlier_rows(group, NUMERIC_STANDARD_COLUMNS),
                "missing_power_W_ratio": float(group["power_W"].isna().mean()),
                "missing_Sq_um_ratio": float(group["Sq_um"].isna().mean()),
                "missing_Sz_um_ratio": float(group["Sz_um"].isna().mean()),
            }
        )
    return pd.DataFrame(rows)


def write_schema_summary(
    path: str | Path,
    unified: pd.DataFrame,
    source_summaries: list[dict[str, Any]],
    quality: pd.DataFrame,
) -> None:
    """Write a Markdown data schema and source-column summary."""
    lines = [
        "# Data Schema Summary",
        "",
        "## Unified Columns",
        "",
        "| column | dtype | missing_ratio |",
        "|---|---:|---:|",
    ]
    for col in unified.columns:
        missing = unified[col].isna().mean() if len(unified) else np.nan
        lines.append(f"| {col} | {unified[col].dtype} | {missing:.4f} |")
    lines.extend(["", "## Source Column Mapping", ""])
    for summary in source_summaries:
        lines.append(f"### {summary['material']} / {summary['source_file']}")
        if summary.get("sheet_name"):
            lines.append(f"- sheet: {summary['sheet_name']}")
        if summary.get("encoding"):
            lines.append(f"- encoding: {summary['encoding']}")
        lines.append(f"- raw shape: {summary['n_rows_raw']} rows x {summary['n_columns_raw']} columns")
        lines.append("- column map:")
        for raw, standard in summary["column_map"].items():
            lines.append(f"  - `{raw}` -> `{standard}`")
        ignored = ", ".join(f"`{c}`" for c in summary["ignored_columns"]) or "none"
        lines.append(f"- ignored columns: {ignored}")
        lines.append("")
    lines.extend(["## Quality Report", "", quality.to_markdown(index=False), ""])
    lines.append("Pulse width columns labelled as fs or with femtosecond-scale values are converted to ps. Spacing columns labelled as mm or with sub-0.1 values are converted to um.")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
