from __future__ import annotations

from typing import Any

from ultrafast_memory.chat.router.manual_override import AVAILABLE_SKILLS
from ultrafast_memory.chat.session_state import (
    get_session_state,
    reset_session_state,
    set_debug_router,
    set_streaming_enabled,
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
    if text == "/no_skill":
        return {"handled": True, "message": "skill routing disabled for this turn"}
    return None
