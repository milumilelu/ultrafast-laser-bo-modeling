from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ultrafast_agent.task_intake import update_task_spec, update_task_spec_contract
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner


def test_agent_native_task_tool_public_import_smoke() -> None:
    assert update_task_spec
    assert update_task_spec_contract
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
    assert identity["legacy_workflow_fallback"] is False
    assert Path(identity["update_task_spec_tool"]).is_relative_to(project_root.resolve())
    assert identity["backend_pid"] > 0
    assert identity["backend_started_at"]
    assert len(identity["git_commit"]) == 40
