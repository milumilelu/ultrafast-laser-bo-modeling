from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ultrafast_memory.chat.router.debug_commands import handle_debug_command
from ultrafast_memory.chat.router.llm_router import llm_route
from ultrafast_memory.chat.router.manual_override import parse_manual_override
from ultrafast_memory.chat.router.rule_router import rule_route
from ultrafast_memory.chat.router.schemas import RoutePlan, fallback_route
from ultrafast_memory.chat.session_state import create_or_get_session_state, update_session_state
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection


def route_message(
    message: str,
    session_id: str,
    message_id: str | None = None,
    use_llm_router: bool = True,
    model_call_sink: Callable[[dict[str, Any]], None] | None = None,
) -> RoutePlan:
    create_or_get_session_state(session_id)
    debug_result = handle_debug_command(message, session_id)
    if debug_result and message.strip() != "/no_skill":
        plan = RoutePlan(
            primary_skill="task_understanding",
            intent="debug_command",
            workflow_stage="debug",
            confidence=1.0,
            reason=debug_result.get("message", "debug command handled"),
            route_source="manual_override",
        )
        _save_and_apply(session_id, message_id, plan)
        return plan

    manual = parse_manual_override(message)
    if manual:
        _save_and_apply(session_id, message_id, manual)
        return manual

    if message.strip() == "/no_skill":
        plan = RoutePlan(
            primary_skill="task_understanding",
            intent="no_skill",
            workflow_stage="chat",
            confidence=1.0,
            reason="Skill routing disabled for this turn.",
            route_source="manual_override",
        )
        _save_and_apply(session_id, message_id, plan)
        return plan

    state = create_or_get_session_state(session_id)
    candidate = rule_route(message, state)
    if candidate and candidate.route_source == "session_state":
        plan = candidate
    elif candidate and candidate.confidence >= 0.9:
        plan = candidate
    elif use_llm_router:
        plan = llm_route(message, state, candidate, model_call_sink=model_call_sink)
    else:
        plan = candidate or fallback_route()
    if not plan:
        plan = fallback_route()
    if plan.route_source == "unknown":
        plan.route_source = "hybrid_router"
    elif plan.route_source == "rule_router" and (not candidate or candidate.confidence < 0.9):
        plan.route_source = "hybrid_router"
    _save_and_apply(session_id, message_id, plan)
    return plan


def save_route_trace(session_id: str, message_id: str | None, route_plan: RoutePlan) -> dict:
    now = utc_now_iso()
    trace = {
        "trace_id": stable_id("routetrace", session_id, message_id or "", route_plan.model_dump(mode="json"), now),
        "session_id": session_id,
        "message_id": message_id,
        "route_source": route_plan.route_source,
        "route_plan_json": json.dumps(route_plan.model_dump(mode="json"), ensure_ascii=False),
        "confidence": route_plan.confidence,
        "created_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_route_trace VALUES (:trace_id, :session_id, :message_id, :route_source, :route_plan_json, :confidence, :created_at)",
            trace,
        )
        conn.commit()
    return trace


def _save_and_apply(session_id: str, message_id: str | None, route_plan: RoutePlan) -> None:
    save_route_trace(session_id, message_id, route_plan)
    update_session_state(session_id, {"suggested_skill_hint": route_plan.model_dump(mode="json")})
