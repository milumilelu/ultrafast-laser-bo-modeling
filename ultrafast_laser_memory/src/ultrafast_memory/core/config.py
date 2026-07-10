from __future__ import annotations

from pathlib import Path
from typing import Any

from ultrafast_shared.config.loader import (
    get_database_path,
    get_project_root,
    load_config as _load_config,
    resolve_path,
)


def load_config(root: Path | None = None) -> dict[str, Any]:
    return _load_config(root)


__all__ = ["get_database_path", "get_project_root", "load_config", "resolve_path"]
