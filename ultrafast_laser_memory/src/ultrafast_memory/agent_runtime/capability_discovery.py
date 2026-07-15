from __future__ import annotations

from typing import Any

from ultrafast_memory.agent_runtime.tool_registry import FOREGROUND_SAFE_TOOL_NAMES


def exposed_tool_names(skills: Any, loaded_skills: list[str]) -> set[str]:
    """All safe capabilities are visible; Skills only influence planner ranking."""
    return set(FOREGROUND_SAFE_TOOL_NAMES)
