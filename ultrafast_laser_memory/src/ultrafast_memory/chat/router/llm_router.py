from __future__ import annotations

import json

from pydantic import ValidationError

from ultrafast_memory.chat.router.schemas import RoutePlan, fallback_route
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.llm.mock import MockLLMClient


def llm_route(message: str, session_state: dict, candidate_route: RoutePlan | None = None) -> RoutePlan:
    cfg = get_llm_config()
    client = create_llm_client(cfg)
    if isinstance(client, MockLLMClient):
        return _candidate_or_fallback(candidate_route)
    prompt = _build_router_prompt(message, session_state, candidate_route)
    try:
        result = client.chat([{"role": "system", "content": prompt}], temperature=0)
        raw = result.get("content") or "{}"
        data = json.loads(raw)
        route = RoutePlan.model_validate(data)
        route.route_source = "llm_router"
        return route
    except (json.JSONDecodeError, ValidationError, Exception):
        return _candidate_or_fallback(candidate_route)


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
        "不要回答用户问题。不要生成加工参数。只能选择已有 skill。信息不足时 requires_clarification=true。\n"
        "Skills: task_understanding, evidence_research, process_planning, "
        "parameter_recommendation, experiment_optimization, result_learning. "
        "输出只是建议，不能激活 Skill 或限制工具。\n"
        f"message={message}\n"
        f"session_state={json.dumps(session_state, ensure_ascii=False)}\n"
        f"candidate_route={json.dumps(candidate, ensure_ascii=False)}"
    )
