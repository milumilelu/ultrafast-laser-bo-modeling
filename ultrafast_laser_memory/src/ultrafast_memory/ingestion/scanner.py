from __future__ import annotations

from pathlib import Path

from ultrafast_memory.core.file_type import detect_file_type


def iter_supported_files(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and detect_file_type(path) != "unknown")
