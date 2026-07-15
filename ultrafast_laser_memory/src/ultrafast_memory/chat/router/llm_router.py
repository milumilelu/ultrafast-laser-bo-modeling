from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from ultrafast_memory.chat.router.schemas import RoutePlan, fallback_route
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.llm.mock import MockLLMClient


def llm_route(
    message: str,
    session_state: dict,
    candidate_route: RoutePlan | None = None,
    model_call_sink: Callable[[dict[str, Any]], None] | None = None,
) -> RoutePlan:
    cfg = get_llm_config()
    client = create_llm_client(cfg)
    if isinstance(client, MockLLMClient):
        return _candidate_or_fallback(candidate_route)
    prompt = _build_router_prompt(message, session_state, candidate_route)
    try:
        _emit_model_call(model_call_sink, client)
        result = client.chat([{"role": "system", "content": prompt}], temperature=0)
        raw = result.get("content") or "{}"
        data = json.loads(raw)
        route = RoutePlan.model_validate(data)
        route.route_source = "llm_router"
        return route
    except (json.JSONDecodeError, ValidationError, Exception):
        return _candidate_or_fallback(candidate_route)


def _emit_model_call(
    sink: Callable[[dict[str, Any]], None] | None,
    client: Any,
) -> None:
    if sink is None:
        return
    try:
        sink({
            "provider": getattr(client, "provider", None),
            "model": getattr(client, "model", None),
            "component": "llm_router",
            "attempt": 1,
        })
    except Exception:  # noqa: BLE001 - observability cannot block routing
        return


def _candidate_or_fallback(candidate_route: RoutePlan | None) -> RoutePlan:
    if candidate_route:
        route = candidate_route.model_copy(deep=True)
        route.route_source = route.route_source or "rule_router"
        return route
    return fallback_route()


def _build_router_prompt(message: str, session_state: dict, candidate_route: RoutePlan | None) -> str:
    candidate = candidate_route.model_dump(mode="json") if candidate_route else None
    return (
        "你是超快激光智能体的路由器。根据用户消息、session_state 和候选规则路由输出 route_plan JSON。"
        "不要回答用户问题，不要生成加工参数或控制工作流；只给出非约束性的 Skill 建议。\n"
        "Skills: task_understanding, evidence_research, process_planning, "
        "parameter_recommendation, experiment_optimization, result_learning. "
        "只输出字段 route_type、primary_skill、secondary_skills、intent、workflow_stage、"
        "confidence、reason、route_source；不能激活 Skill、限制工具、声明证据状态或要求权限。\n"
        f"message={message}\n"
        f"session_state={json.dumps(session_state, ensure_ascii=False)}\n"
        f"candidate_route={json.dumps(candidate, ensure_ascii=False)}"
    )
