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
    import ultrafast_memory.agent_runtime.main_agent_loop as main_agent_loop
    import ultrafast_memory.agent_runtime.planner as planner
    import ultrafast_memory.agent_runtime.skill_registry as skill_registry
    import ultrafast_memory.agent_runtime.tool_registry as tool_registry

    project_root = Path(__file__).resolve().parents[3]
    return {
        "runtime_mode": "capability_discovery",
        "git_commit": _git_commit(project_root),
        "git_branch": _git_value(project_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "git_dirty": bool(_git_value(project_root, ["status", "--porcelain"])),
        "python": str(Path(sys.executable).resolve()),
        "package_root": str((project_root / "src").resolve()),
        "main_agent_loop": str(Path(main_agent_loop.__file__).resolve()),
        "main_agent_planner": str(Path(planner.__file__).resolve()),
        "skill_registry": str(Path(skill_registry.__file__).resolve()),
        "tool_registry": str(Path(tool_registry.__file__).resolve()),
        "update_task_spec_tool": str(Path(update_task_spec_tool.__file__).resolve()),
        "legacy_workflow_fallback": False,
        "backend_pid": os.getpid(),
        "backend_started_at": BACKEND_STARTED_AT,
    }


def _git_commit(project_root: Path) -> str:
    return _git_value(project_root, ["rev-parse", "HEAD"]) or "unknown"


def _git_value(project_root: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=project_root,
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
