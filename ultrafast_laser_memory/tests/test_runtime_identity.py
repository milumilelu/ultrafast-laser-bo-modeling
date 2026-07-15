from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner


def test_agent_runtime_public_import_smoke() -> None:
    assert MainAgentPlanner


def test_health_exposes_loaded_runtime_identity(project_root: Path) -> None:
    health = TestClient(app).get("/health").json()
    identity = health["runtime_identity"]

    assert health["agent_capability_contract"] == "skill-discovery-v2"
    assert Path(identity["python"]).resolve() == Path(sys.executable).resolve()
    assert Path(identity["package_root"]).resolve() == (project_root / "src").resolve()
    assert Path(identity["main_agent_loop"]).is_relative_to(project_root.resolve())
    assert identity["runtime_mode"] == "capability_discovery"
    assert Path(identity["main_agent_planner"]).is_relative_to(project_root.resolve())
    assert Path(identity["skill_registry"]).is_relative_to(project_root.resolve())
    assert Path(identity["tool_registry"]).is_relative_to(project_root.resolve())
    assert Path(identity["working_context"]).is_relative_to(project_root.resolve())
    assert identity["backend_pid"] > 0
    assert identity["backend_started_at"]
    assert len(identity["git_commit"]) == 40
