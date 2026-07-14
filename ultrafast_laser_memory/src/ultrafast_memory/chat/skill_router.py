from __future__ import annotations

from ultrafast_memory.chat.router.rule_router import rule_route


def route_skill(message: str) -> dict:
    route = rule_route(message, None)
    if not route:
        return {"selected_skill": "task_understanding", "confidence": 0.5, "reason": "default hint"}
    return {
        "selected_skill": route.primary_skill,
        "confidence": route.confidence,
        "reason": route.reason,
    }
