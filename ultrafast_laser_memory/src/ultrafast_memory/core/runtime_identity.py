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
    import ultrafast_agent.task_intake.update_task_spec_tool as update_task_spec_tool
    import ultrafast_memory.process_workflow.agent_controller as agent_controller
    import ultrafast_memory.chat.main_agent_loop as main_agent_loop

    project_root = Path(__file__).resolve().parents[3]
    return {
        "git_commit": _git_commit(project_root),
        "python": str(Path(sys.executable).resolve()),
        "package_root": str((project_root / "src").resolve()),
        "main_agent_loop": str(Path(main_agent_loop.__file__).resolve()),
        "main_agent_controller": str(Path(agent_controller.__file__).resolve()),
        "update_task_spec_tool": str(Path(update_task_spec_tool.__file__).resolve()),
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
