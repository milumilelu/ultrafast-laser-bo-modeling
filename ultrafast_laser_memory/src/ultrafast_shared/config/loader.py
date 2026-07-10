from __future__ import annotations

import json
import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


ENV_CONFIG_MAP = {
    "ULTRAFAST_DATABASE_URL": ("database", "url"),
    "ULTRAFAST_DEMO_MODE": ("demo", "enabled"),
    "ULTRAFAST_OBSERVABILITY_MODE": ("observability", "display_mode"),
}


def get_project_root() -> Path:
    return Path(os.environ.get("ULTRAFAST_MEMORY_ROOT", Path.cwd())).resolve()


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return value


def _coerce_env(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _nested(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    cursor = result
    for key in path[:-1]:
        child: dict[str, Any] = {}
        cursor[key] = child
        cursor = child
    cursor[path[-1]] = value
    return result


def _environment_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    raw = env.get("ULTRAFAST_CONFIG_OVERRIDES")
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("ULTRAFAST_CONFIG_OVERRIDES must be a JSON object")
        result = deep_merge(result, parsed)
    for name, path in ENV_CONFIG_MAP.items():
        if name in env:
            result = deep_merge(result, _nested(path, _coerce_env(env[name])))
    return result


def _file_revision(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _environment_signature(env: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    names = ("ULTRAFAST_CONFIG_OVERRIDES", *ENV_CONFIG_MAP)
    return tuple((name, env[name]) for name in names if name in env)


@lru_cache(maxsize=32)
def _load_revision_cached(
    base_text: str,
    default_revision: tuple[int, int] | None,
    local_revision: tuple[int, int] | None,
    environment_signature: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    # Revisions are part of the key; reads happen only when a file or relevant env value changes.
    del default_revision, local_revision
    base = Path(base_text)
    config = _read_yaml(base / "configs/default.yaml")
    config = deep_merge(config, _read_yaml(base / "configs/local.yaml"))
    config = deep_merge(config, _environment_overrides(dict(environment_signature)))
    return config


def load_config(
    root: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base = (root or get_project_root()).resolve()
    environment = env or os.environ
    config = deepcopy(
        _load_revision_cached(
            str(base),
            _file_revision(base / "configs/default.yaml"),
            _file_revision(base / "configs/local.yaml"),
            _environment_signature(environment),
        )
    )
    if cli_overrides:
        config = deep_merge(config, cli_overrides)
    return config


def resolve_path(path: str | Path, root: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ((root or get_project_root()) / candidate).resolve()


def get_database_path(root: Path | None = None) -> Path:
    config = load_config(root)
    url = config.get("database", {}).get("url", "sqlite:///data/ultrafast_memory.db")
    if not isinstance(url, str) or not url.startswith("sqlite:///"):
        raise ValueError("only sqlite:/// database URLs are supported")
    return resolve_path(url.removeprefix("sqlite:///"), root)
