from __future__ import annotations

from pathlib import Path


def detect_file_type(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    name = path.name.lower()
    path_text = str(path).replace("\\", "/").lower()
    if suffix == ".json":
        return "json_recipe"
    if suffix == ".csv":
        return "measurement_csv"
    if suffix == ".log":
        return "machine_log"
    if suffix == ".txt":
        if "notes" in path_text or "note" in name:
            return "operator_note"
        return "machine_log"
    return "unknown"
