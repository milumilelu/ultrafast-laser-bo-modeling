from __future__ import annotations

from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.chat.router.schemas import RoutePlan


AVAILABLE_SKILLS = {
    item.name: item.description for item in get_default_skill_registry().list()
}


def parse_manual_override(message: str) -> RoutePlan | None:
    text = message.strip()
    if not text.startswith("/skill "):
        return None
    requested = text.split(maxsplit=1)[1].strip()
    try:
        skill = get_default_skill_registry().get(requested).name
    except KeyError:
        return RoutePlan(
            primary_skill="task_understanding", intent="manual_override_invalid",
            workflow_stage="agent_planning", confidence=0.2,
            reason=f"Unknown skill hint: {requested}", requires_clarification=True,
            clarification_questions=[f"可用 skill: {', '.join(AVAILABLE_SKILLS)}"],
            route_source="manual_override",
        )
    return RoutePlan(
        primary_skill=skill, intent="manual_skill_hint", workflow_stage="agent_planning",
        confidence=1.0, reason="User supplied an explicit non-binding Skill hint.",
        route_source="manual_override",
    )
