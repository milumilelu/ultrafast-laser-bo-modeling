from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture()
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def isolated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ULTRAFAST_MEMORY_ROOT", str(tmp_path))
    (tmp_path / "configs").mkdir()
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture()
def isolated_examples(tmp_path: Path, project_root: Path) -> Path:
    dest = tmp_path / "examples"
    shutil.copytree(project_root / "examples", dest)
    return dest
