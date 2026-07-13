from __future__ import annotations

from typing import Any

from ultrafast_memory.chat.router.manual_override import AVAILABLE_SKILLS
from ultrafast_agent.skills import get_default_skill_registry
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
        skills = {item.name: {"version": item.version, "purpose": item.purpose,
                             "allowed_tools": list(item.allowed_tools)}
                  for item in get_default_skill_registry().list()}
        return {"handled": True, "message": "registered skill inventory", "skills": skills}
    if text == "/tools":
        return {"handled": True, "message": "V3 tool inventory", "tools": [
            "equipment_memory_tool", "rag_query_tool", "historical_case_tool", "process_rule_tool",
            "trial_template_tool", "knowledge_approval_tool", "bo_parameter_recommendation_tool",
            "rag_parameter_recommendation_tool", "llm_fallback_parameter_tool",
            "parameter_constraint_validation_tool", "parameter_provenance_registry_tool",
            "experiment_store_tool", "measurement_parser_tool", "quality_metric_tool", "model_snapshot_tool"]}
    if text in {"/reasoning", "/waterfall", "/campaign", "/model"}:
        return {"handled": True, "message": text[1:] + " public view", "state": get_session_state(session_id)}
    if text == "/no_skill":
        return {"handled": True, "message": "skill routing disabled for this turn"}
    return None
