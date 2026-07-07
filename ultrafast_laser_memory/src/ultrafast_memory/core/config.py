from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def get_project_root() -> Path:
    return Path(os.environ.get("ULTRAFAST_MEMORY_ROOT", Path.cwd())).resolve()


def load_config(root: Path | None = None) -> dict[str, Any]:
    base = (root or get_project_root()).resolve()
    config_path = base / "configs" / "default.yaml"
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_path(path: str | Path, root: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ((root or get_project_root()) / candidate).resolve()


def get_database_path(root: Path | None = None) -> Path:
    cfg = load_config(root)
    url = cfg.get("database", {}).get("url", "sqlite:///data/ultrafast_memory.db")
    if not url.startswith("sqlite:///"):
        raise ValueError("MVP only supports sqlite:/// database URLs")
    return resolve_path(url.replace("sqlite:///", "", 1), root)
