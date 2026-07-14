from __future__ import annotations

from typing import Any

from ultrafast_memory.agent_runtime.tool_registry import BASE_TOOL_NAMES


def exposed_tool_names(skills: Any, loaded_skills: list[str]) -> set[str]:
    """Expose base tools plus tools recommended by explicitly loaded Skills."""
    names = set(BASE_TOOL_NAMES)
    for skill_name in loaded_skills:
        names.update(skills.get(skill_name).recommended_tools)
    return names
