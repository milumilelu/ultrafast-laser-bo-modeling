from __future__ import annotations

from ultrafast_agent.skills import get_default_skill_registry


def build_skill_registry():
    """Return the authoritative discoverable Skill registry."""
    return get_default_skill_registry()
