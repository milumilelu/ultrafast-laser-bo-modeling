from __future__ import annotations

from typing import Any

from ultrafast_memory.chat.router.manual_override import AVAILABLE_SKILLS
from ultrafast_memory.chat.debug_views import (
    campaign_view,
    model_view,
    reasoning_view,
    waterfall_view,
)
from ultrafast_agent.skills import get_default_skill_registry
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.agent_runtime.capability_discovery import exposed_tool_names
from ultrafast_memory.chat.session_state import (
    get_session_state,
    reset_session_state,
    set_debug_router,
    set_streaming_enabled,
    update_session_state,
)


def handle_debug_command(message: str, session_id: str) -> dict[str, Any] | None:
    text = message.strip()
    if text == "/debug router on":
        set_debug_router(session_id, True)
        return {"handled": True, "message": "router debug enabled", "state": get_session_state(session_id)}
    if text == "/debug router off":
        set_debug_router(session_id, False)
        return {"handled": True, "message": "router debug disabled", "state": get_session_state(session_id)}
    if text == "/stream on":
        set_streaming_enabled(session_id, True)
        return {"handled": True, "message": "streaming enabled", "state": get_session_state(session_id)}
    if text == "/stream off":
        set_streaming_enabled(session_id, False)
        return {"handled": True, "message": "streaming disabled", "state": get_session_state(session_id)}
    if text == "/state":
        return {"handled": True, "message": "session state", "state": get_session_state(session_id)}
    if text == "/reset":
        reset_session_state(session_id)
        return {"handled": True, "message": "session state reset", "state": get_session_state(session_id)}
    if text == "/routes":
        return {"handled": True, "message": "available routes", "routes": AVAILABLE_SKILLS}
    if text in {"/trace summary", "/trace full", "/trace off"}:
        level = text.split()[-1]
        current = get_session_state(session_id)
        slots = dict(current.get("collected_slots") or {})
        slots["public_trace_mode"] = level
        update_session_state(session_id, {"collected_slots": slots})
        return {"handled": True, "message": f"public trace mode: {level}", "trace_mode": level,
                "note": "hidden chain-of-thought is never exposed"}
    if text == "/skills":
        state = get_session_state(session_id)
        active = set(state.get("active_skills_json") or [])
        skills = {item.name: {"version": item.version, "description": item.description,
                             "recommended_tools": list(item.recommended_tools),
                             "loaded": item.name in active}
                  for item in get_default_skill_registry().list()}
        return {"handled": True, "message": "registered skill inventory", "skills": skills}
    if text == "/tools":
        skill_registry = get_default_skill_registry()
        state = get_session_state(session_id)
        discoverable = exposed_tool_names(skill_registry, list(state.get("active_skills_json") or []))
        tools = [{**item, "discoverable": item["name"] in discoverable}
                 for item in build_main_agent_tool_registry().schemas_for_agent()]
        return {"handled": True, "message": "Agent tool inventory", "tools": tools}
    if text == "/reasoning":
        return {"handled": True, "message": "公开推理摘要", **reasoning_view(session_id)}
    if text == "/waterfall":
        return {"handled": True, "message": "执行耗时瀑布", **waterfall_view(session_id)}
    if text == "/campaign":
        return {"handled": True, "message": "优化 Campaign", **campaign_view(session_id)}
    if text == "/model":
        return {"handled": True, "message": "模型快照", **model_view(session_id)}
    if text == "/no_skill":
        return {"handled": True, "message": "skill routing disabled for this turn"}
    return None
