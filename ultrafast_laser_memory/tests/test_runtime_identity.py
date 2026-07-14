from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ultrafast_agent.task_intake import (
    LLMStructuredExtractor,
    StrictKeyValueParser,
    TaskFieldExtractionService,
)
from ultrafast_memory.apps.api.main import app


def test_task_intake_public_import_smoke() -> None:
    assert TaskFieldExtractionService
    assert LLMStructuredExtractor
    assert StrictKeyValueParser


def test_health_exposes_loaded_runtime_identity(project_root: Path) -> None:
    health = TestClient(app).get("/health").json()
    identity = health["runtime_identity"]

    assert health["task_intake_contract"] == "llm-structured-v1"
    assert Path(identity["python"]).resolve() == Path(sys.executable).resolve()
    assert Path(identity["package_root"]).resolve() == (project_root / "src").resolve()
    assert Path(identity["chat_orchestrator"]).is_relative_to(project_root.resolve())
    assert Path(identity["task_intake_service"]).is_relative_to(project_root.resolve())
    assert Path(identity["llm_extractor"]).is_relative_to(project_root.resolve())
    assert identity["backend_pid"] > 0
    assert identity["backend_started_at"]
    assert len(identity["git_commit"]) == 40
