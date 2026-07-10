from __future__ import annotations

import ast
import re
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_domain_does_not_depend_on_transports_or_infrastructure(project_root):
    forbidden = ("fastapi", "ultrafast_memory.app", "ultrafast_integrations", "sqlalchemy")
    violations = []
    for path in (project_root / "src/ultrafast_domain").rglob("*.py"):
        for name in _imports(path):
            if name.startswith(forbidden):
                violations.append(f"{path.relative_to(project_root)} -> {name}")
    assert violations == []


def test_bo_does_not_depend_on_chat_or_rag(project_root):
    violations = []
    for path in (project_root / "src/ultrafast_bo").rglob("*.py"):
        for name in _imports(path):
            if "chat" in name or "rag" in name or name.startswith("fastapi"):
                violations.append(f"{path.relative_to(project_root)} -> {name}")
    assert violations == []


def test_fastapi_transport_contains_no_direct_sql(project_root):
    wrapper = (project_root / "src/ultrafast_memory/app/api.py").read_text(encoding="utf-8")
    assert "ultrafast_memory.apps.api.main" in wrapper
    assert len(wrapper.splitlines()) <= 7
    router_root = project_root / "src/ultrafast_memory/apps/api/routers"
    routers = list(router_root.glob("*.py"))
    assert len(routers) >= 10
    for path in routers:
        source = path.read_text(encoding="utf-8")
        assert "get_connection" not in source
        assert re.search(r"\b(?:conn|connection)\.execute\(", source) is None
        assert re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\s+", source) is None
