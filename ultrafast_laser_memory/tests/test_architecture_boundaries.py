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
    forbidden = ("fastapi", "ultrafast_memory.app", "ultrafast_integrations", "sqlalchemy", "openai", "paddleocr")
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
    assert not (project_root / "src/ultrafast_memory/app/api.py").exists()
    main = (project_root / "src/ultrafast_memory/apps/api/main.py").read_text(encoding="utf-8")
    assert "create_app" in main
    router_root = project_root / "src/ultrafast_memory/apps/api/routers"
    routers = list(router_root.glob("*.py"))
    assert len(routers) >= 10
    for path in routers:
        source = path.read_text(encoding="utf-8")
        assert "get_connection" not in source
        assert re.search(r"\b(?:conn|connection)\.execute\(", source) is None
        assert re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\s+", source) is None


def test_integrations_do_not_import_application_service_modules(project_root):
    violations = []
    for path in (project_root / "src/ultrafast_integrations").rglob("*.py"):
        for name in _imports(path):
            if name.startswith(("ultrafast_agent.", "ultrafast_bo.application.")) and not name.endswith((".models", ".events")):
                violations.append(f"{path.relative_to(project_root)} -> {name}")
            if name.startswith("ultrafast_memory.") and name.endswith(".service"):
                violations.append(f"{path.relative_to(project_root)} -> {name}")
    assert violations == []


def test_legacy_bo_adapters_do_not_reimplement_model_or_acquisition(project_root):
    compatibility = (project_root / "src/ultrafast_bo/application/compatibility.py").read_text(encoding="utf-8")
    assert "GaussianProcessRegressor" not in compatibility
    assert "Matern(" not in compatibility
    root = project_root.parent
    for relative in ("src/interactive_bo.py", "src/bayes_opt.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "GaussianProcessRegressor" not in source
        assert "Matern(" not in source
        assert "BORecommendationService" in source


def test_experimental_vision_has_no_chat_or_public_api_registration(project_root):
    paths = [
        *list((project_root / "src/ultrafast_memory/apps/api/routers").glob("*.py")),
        *list((project_root / "src/ultrafast_memory/chat").rglob("*.py")),
    ]
    assert all("ultrafast_integrations.vision" not in path.read_text(encoding="utf-8") for path in paths)


def test_new_legacy_compatibility_modules_define_no_services(project_root):
    for relative in (
        "src/ultrafast_memory/process_recommendations/service.py",
        "src/ultrafast_memory/documents/service.py",
    ):
        tree = ast.parse((project_root / relative).read_text(encoding="utf-8"))
        assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)
