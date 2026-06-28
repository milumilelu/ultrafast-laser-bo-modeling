"""Input/output helpers for tabular experiment files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin1")


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file."""
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_directories(root: Path) -> dict[str, Path]:
    """Create and return the standard output directories."""
    dirs = {
        "data_processed": root / "data" / "processed",
        "outputs": root / "outputs",
        "figures": root / "figures",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def read_csv_robust(path: Path) -> tuple[pd.DataFrame, str]:
    """Read a CSV file by trying common encodings used in lab exports."""
    errors: list[str] = []
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding), encoding
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"Unable to read CSV file {path}. Tried encodings: {errors}")


def read_table(path: str | Path) -> list[tuple[pd.DataFrame, dict[str, Any]]]:
    """Read CSV or Excel files and return dataframes with source metadata."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df, encoding = read_csv_robust(p)
        return [(df, {"source_file": p.name, "sheet_name": None, "encoding": encoding})]
    if suffix in {".xlsx", ".xls"}:
        engine = "openpyxl" if suffix == ".xlsx" else None
        excel = pd.ExcelFile(p, engine=engine)
        tables = []
        for sheet in excel.sheet_names:
            df = pd.read_excel(p, sheet_name=sheet, engine=engine)
            tables.append((df, {"source_file": p.name, "sheet_name": sheet, "encoding": None}))
        return tables
    raise ValueError(f"Unsupported input file type: {p}")


def resolve_input_files(config: dict[str, Any], root: Path) -> dict[str, Path]:
    """Resolve material-to-file mappings from the config without hard-coded paths."""
    raw = config.get("input_files", {})
    if isinstance(raw, list):
        return {Path(item).stem: (root / item).resolve() for item in raw}
    if isinstance(raw, dict):
        return {str(material): (root / str(path)).resolve() for material, path in raw.items()}
    raise ValueError("config.input_files must be a list or a mapping")


def setup_logging(output_dir: Path) -> logging.Logger:
    """Configure file and console logging."""
    logger = logging.getLogger("laser_modeling")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(output_dir / "run_log.txt", encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
