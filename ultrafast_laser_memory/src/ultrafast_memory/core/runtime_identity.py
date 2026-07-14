from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_STARTED_AT = datetime.now(timezone.utc).isoformat()


def runtime_identity() -> dict[str, Any]:
    """Return the exact interpreter and source files loaded by this backend process."""
    import ultrafast_agent.task_intake.extraction_service as extraction_service
    import ultrafast_agent.task_intake.llm_extractor as llm_extractor
    import ultrafast_memory.process_workflow.chat_orchestrator as chat_orchestrator

    project_root = Path(__file__).resolve().parents[3]
    return {
        "git_commit": _git_commit(project_root),
        "python": str(Path(sys.executable).resolve()),
        "package_root": str((project_root / "src").resolve()),
        "chat_orchestrator": str(Path(chat_orchestrator.__file__).resolve()),
        "task_intake_service": str(Path(extraction_service.__file__).resolve()),
        "llm_extractor": str(Path(llm_extractor.__file__).resolve()),
        "backend_pid": os.getpid(),
        "backend_started_at": BACKEND_STARTED_AT,
    }


def _git_commit(project_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
