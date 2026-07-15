from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from time import monotonic
from typing import Any

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.actions import AgentAction
from ultrafast_memory.agent_runtime.capability_discovery import exposed_tool_names
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.skill_registry import build_skill_registry
from ultrafast_memory.agent_runtime.task_intake import prepare_task_context
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.agent_runtime.working_context import (
    ContextPersistenceService,
    WorkingContext,
    load_working_context,
)
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.equipment.bounds import build_machine_bounds


MAX_PLANNER_DECISIONS_PER_TURN = 6
MAX_MODEL_CALLS_PER_TURN = 6


def run_main_agent_turn(
    *, session_id: str, message: str, message_id: str | None, client: Any,
    suggested_skills: list[str] | None = None, active_skills: list[str] | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    document_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the single foreground control loop until a semantic terminal action."""
    turn_started = monotonic()
    registry = build_main_agent_tool_registry()
    executor = ToolExecutor(registry)
    skills = build_skill_registry()
    planner = MainAgentPlanner(client)
    state = get_session_state(session_id)
    working = load_working_context(state)
    observations = working.observations
    turn_observation_offset = len(observations)
    tool_calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    final_action: AgentAction | None = None
    model_call_count = 0
    planner_call_count = 0
    repair_count = 0
    max_prompt_chars = 0
    first_event_latency_ms: float | None = None
    total_decisions = int(state.get("agent_decision_count") or 0)
    repeated_no_progress: dict[str, int] = {}
    recent_actions: list[dict[str, Any]] = []
    deterministic_only = False

    if document_context is not None:
        document_observation = {
            "type": "DocumentObservation",
            "status": str(document_context.get("status") or "loaded"),
            **document_context,
        }
        if document_context.get("status") == "loaded":
            document_id = document_context.get("document_id")
            if not any(item.get("document_id") == document_id for item in working.documents):
                working.documents.append(dict(document_context))
            if not any(item.get("type") == "DocumentObservation" and item.get("document_id") == document_id
                       for item in observations):
                observations.append(document_observation)
            _persist_context_nonblocking(
                session_id, message_id, working, ["documents", "observations"],
                events, event_sink, warnings,
            )
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "document_loaded", "document_input", "加工需求文档已读取",
                f"已提取 {document_context.get('file_name')}，正在交给主 Agent 解析。",
                "completed", {"document": document_context}, warnings,
            ))
        else:
            observations.append(document_observation)
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "warning", "document_input", "加工需求文档读取失败",
                str(document_context.get("error") or "文档读取失败。"),
                "completed", {"document": document_context}, warnings,
            ))

    _publish(events, event_sink, _safe_trace(
        session_id, message_id, "agent_started", "main_agent", "主 Agent 已启动",
        "已读取当前 Working Context，开始推进任务。", "running", {}, warnings,
    ))
    first_event_latency_ms = round((monotonic() - turn_started) * 1000, 3)

    preparation = prepare_task_context(message, working.model_dump(mode="json"))
    prepared_paths = working.apply(preparation.context_updates)
    loaded = _select_skill_names(
        skills,
        explicit=active_skills or [],
        suggested=suggested_skills or [],
        prepared=preparation.skill_hints,
        task=working.task,
        observations=observations,
    )
    working.active_skills = loaded
    if prepared_paths or loaded:
        _persist_context_nonblocking(
            session_id, message_id, working,
            [*prepared_paths, "active_skills"], events, event_sink, warnings,
        )
    _publish(events, event_sink, _safe_trace(
        session_id, message_id, "task_context_prepared", "request_intake", "任务上下文已准备",
        preparation.summary, "completed",
        {
            "changed_paths": prepared_paths,
            "task_fields": preparation.changed_fields,
            "conflicts": preparation.conflicts,
            "ambiguities": preparation.ambiguities,
            "blocking_fields": preparation.blocking_fields,
            "injected_skills": loaded,
        }, warnings,
    ))
    if preparation.blocking_fields and (
        client is None or getattr(client, "provider", None) == "mock"
    ):
        final_action = _fallback_blocking_action(preparation.blocking_fields)

    turn_step = 0
    while final_action is None:
        turn_step += 1
        if turn_step > MAX_PLANNER_DECISIONS_PER_TURN:
            final_action = AgentAction(
                action="respond", decision_summary="达到单轮 Planner 硬上限，已触发安全 fallback。",
                message=(
                    "本轮已达到规划调用上限，当前上下文和 Observation 均已保留。"
                    "这不表示任务完成。NextAction：补充新事实或在下一轮继续。"
                ),
            )
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "probable_agent_loop", "main_agent", "检测到规划循环",
                final_action.decision_summary, "completed", {"recent_actions": recent_actions[-8:]}, warnings,
            ))
            break

        exposed = exposed_tool_names(skills, loaded)
        tool_schemas = _rank_tool_schemas(registry.schemas_for_agent(exposed), skills, loaded)
        if model_call_count >= MAX_MODEL_CALLS_PER_TURN:
            final_action = planner.deterministic_fallback(
                _planner_context(working),
                _planner_observations(observations, turn_observation_offset),
                [str(item["name"]) for item in tool_schemas],
                reason="model_call_limit_reached",
            )
            break
        planning = _safe_trace(
            session_id, message_id, "agent_planning_started", "main_agent", "主 Agent 规划",
            "正在根据 Working Context 和最新观察规划下一动作。", "running", {"sequence": turn_step}, warnings,
        )
        _publish(events, event_sink, planning)

        def publish_planner_model_call(call: dict[str, Any]) -> None:
            nonlocal model_call_count, repair_count, max_prompt_chars
            event_type = str(call.get("event_type") or "model_call_started")
            if event_type == "model_call_started":
                model_call_count += 1
                if bool(call.get("repair")):
                    repair_count += 1
                max_prompt_chars = max(max_prompt_chars, int(call.get("prompt_chars") or 0))
            provider = str(call.get("provider") or "unknown-provider")
            model = str(call.get("model") or "unknown-model")
            attempt = int(call.get("attempt") or 1)
            model_name = f"{provider}/{model}"
            titles = {
                "model_call_started": f"调用模型 {model_name}",
                "model_provider_response_received": f"模型 {model_name} 已返回",
                "model_parse_completed": "模型输出解析完成",
                "model_validation_completed": "模型行动校验完成",
                "model_call_completed": f"模型调用完成：{model_name}",
                "model_call_failed": f"模型调用失败：{model_name}",
            }
            summaries = {
                "model_call_started": (
                    f"等待模型 {model_name} 返回主 Agent 下一动作；"
                    f"调用序号 {call.get('call_sequence') or model_call_count}，第 {attempt}/2 次尝试，"
                    f"输入 {call.get('prompt_chars') or 0} 字符。"
                ),
                "model_provider_response_received": (
                    f"模型完整响应已返回：{call.get('response_chars') or 0} 字符，"
                    f"耗时 {call.get('duration_ms') or 0} ms。"
                ),
                "model_parse_completed": (
                    f"结构化输出解析成功，耗时 {call.get('duration_ms') or 0} ms。"
                ),
                "model_validation_completed": (
                    f"行动校验通过：{call.get('action') or 'unknown'}"
                    + (f" → {call.get('tool_name')}" if call.get("tool_name") else "")
                    + f"，耗时 {call.get('duration_ms') or 0} ms。"
                ),
                "model_call_completed": (
                    f"主 Agent 模型调用完成，总耗时 {call.get('duration_ms') or 0} ms。"
                ),
                "model_call_failed": (
                    f"模型调用在 {call.get('failure_stage') or 'unknown'} 阶段失败；"
                    + ("将按结构化修复提示重试。" if call.get("will_retry") else "已停止重试。")
                ),
            }
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, event_type, "agent_planning",
                titles.get(event_type, "模型调用状态"),
                summaries.get(event_type, "模型调用状态已更新。"),
                "running" if event_type == "model_call_started" else "completed", call, warnings,
            ))

        planner_call_count += 1
        if deterministic_only:
            action = planner.deterministic_fallback(
                _planner_context(working),
                _planner_observations(observations, turn_observation_offset),
                [str(item["name"]) for item in tool_schemas],
                reason="planner_repair_exhausted",
            )
        else:
            action = planner.decide(
                message=message,
                working_context=_planner_context(working),
                available_tools=tool_schemas,
                active_skills=loaded,
                recent_tool_results=_planner_observations(observations, turn_observation_offset),
                skill_guidance=_skill_guidance(skills, loaded),
                runtime_hints={
                    "suggested_skills": suggested_skills or [],
                    "router_is_hint_only": True,
                    "repair_allowed": repair_count < 1,
                },
                model_call_sink=publish_planner_model_call,
            )
            if action.provider == "deterministic_fallback" and action.error_details:
                deterministic_only = True
        final_action = action
        total_decisions += 1
        recent_actions.append({"action": action.action, "tool": action.tool_name, "arguments": action.arguments})
        _publish(events, event_sink, _safe_trace(
            session_id, message_id, "agent_decision", "main_agent", "主 Agent 决策",
            action.decision_summary, "completed",
            {"action": action.action, "sequence": turn_step,
             "skills_used": action.skills_used,
             **({"validation_errors": action.error_details} if action.error_details else {})}, warnings,
            skill=action.skills_used[0] if action.skills_used else None, tool=action.tool_name,
        ))

        changed = working.apply(action.context_updates)
        if changed:
            _persist_context_nonblocking(
                session_id, message_id, working, changed, events, event_sink, warnings,
            )

        if action.action == "update_context":
            final_action = None
            if not changed:
                final_action = planner.deterministic_fallback(
                    _planner_context(working),
                    _planner_observations(observations, turn_observation_offset),
                    [str(item["name"]) for item in tool_schemas],
                    reason="update_context_without_progress",
                )
                break
            continue
        if action.action != "call_tool":
            break
        final_action = None

        tool_name = str(action.tool_name)
        contract = registry.get(tool_name)
        equipment = working.equipment_context or build_machine_bounds()
        cached = _cached_observation(
            observations, turn_observation_offset, tool_name, action.arguments,
            contract.cache_policy, equipment,
        )
        if cached is None:
            cached = _duplicate_turn_observation(
                observations, turn_observation_offset, tool_name, action.arguments,
            )
        duplicate_key = json.dumps({"tool": tool_name, "arguments": action.arguments}, ensure_ascii=False, sort_keys=True, default=str)
        if cached is not None:
            repeated_no_progress[duplicate_key] = repeated_no_progress.get(duplicate_key, 0) + 1
            cached.setdefault("meta", {})["reused_existing_observation"] = True
            observations.append(cached)
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "tool_cache_hit", "main_agent", f"复用 {tool_name} 已有观察",
                "相同 Tool 与参数已有等价结果，未重复执行；该观察已返回 Planner。", "completed",
                {"arguments": _public_tool_arguments(action.arguments),
                 "observation": _public_tool_observation(tool_name, cached)}, warnings, tool=tool_name,
            ))
            if repeated_no_progress[duplicate_key] >= 3:
                final_action = AgentAction(
                    action="respond", decision_summary="同一 Tool 观察连续未产生上下文进展，判定 probable planning loop。",
                    message=(
                        "同一工具结果被连续复用且未带来新进展，已停止 probable planning loop。"
                        "现有上下文和工具观察均已保留；可在下一轮补充新事实或要求改用其他证据来源。"
                    ),
                    provider=action.provider, model=action.model,
                )
                _publish(events, event_sink, _safe_trace(
                    session_id, message_id, "probable_agent_loop", "main_agent", "无进展循环已停止",
                    final_action.decision_summary, "completed", {"tool": tool_name, "arguments": action.arguments}, warnings,
                ))
                break
            continue

        _publish(events, event_sink, _safe_trace(
            session_id, message_id, "tool_call_started", "main_agent", f"调用 {tool_name}",
            f"等待工具 {tool_name} 返回：{contract.purpose}", "running",
            {"arguments": _public_tool_arguments(action.arguments)}, warnings, tool=tool_name,
        ))
        approved, approval_observation = _scoped_user_approval(message, message_id, tool_name, action.arguments)
        if approval_observation:
            observations.append(approval_observation)
        tool_started = monotonic()
        execution = executor.execute(
            tool_name, action.arguments,
            {
                "session_id": session_id, "message_id": message_id, "user_message": message,
                "working_context": working.model_dump(mode="json"), "task_spec": working.task,
                "equipment_snapshot": equipment, "human_approved": approved,
            },
        )
        envelope = execution.to_tool_result(tool_name)
        tool_duration_ms = round((monotonic() - tool_started) * 1000, 3)
        envelope.setdefault("meta", {}).update({
            "arguments": deepcopy(action.arguments), "cache_policy": contract.cache_policy,
            "cache_hit": False, "wall_duration_ms": tool_duration_ms,
        })
        tool_calls.append({
            "step": turn_step, "tool_name": tool_name, "arguments": action.arguments,
            "result": envelope, "status": envelope["status"], "cache_hit": False,
        })
        observations.append(envelope)
        if tool_name == "get_equipment_context" and envelope["status"] == "success":
            data = envelope.get("data") or {}
            working.equipment_context = {key: value for key, value in data.items() if key != "status"}
        _publish(events, event_sink, _safe_trace(
            session_id, message_id,
            "tool_completed" if envelope["status"] not in {"failed", "blocked", "validation_error"} else "tool_failed",
            "main_agent", f"{tool_name} 执行结果",
            envelope.get("summary") or ("工具执行完成。" if envelope["status"] != "failed" else "工具执行失败。"),
            "completed", {
                "arguments": _public_tool_arguments(action.arguments),
                "observation": _public_tool_observation(tool_name, envelope),
                "duration_ms": tool_duration_ms,
            }, warnings, tool=tool_name,
        ))
        if tool_name == "record_process_result":
            try:
                _run_result_postprocess_hooks(action.arguments, envelope, working)
            except Exception as exc:  # noqa: BLE001 - governance/postprocess is a sidecar
                warning = f"结果后处理失败：{type(exc).__name__}"
                warnings.append(warning)
                _publish(events, event_sink, _safe_trace(
                    session_id, message_id, "warning", "postprocess", "结果后处理警告",
                    warning + "；当前加工结果和 Agent 主线继续。", "completed", {}, warnings,
                ))
        _persist_context_nonblocking(session_id, message_id, working, ["observations"], events, event_sink, warnings)

    if final_action is None:
        raise RuntimeError("main agent produced no action")
    working.active_skills = loaded
    _persist_context_nonblocking(
        session_id, message_id, working, ["final_action"], events, event_sink, warnings,
        final_action=final_action.model_dump(mode="json"), decision_count=total_decisions,
    )
    exposed = exposed_tool_names(skills, loaded)
    critical_missing = _critical_missing(working.task)
    workflow = {
        "runtime_mode": "capability_discovery",
        "task_spec": working.task,
        "working_context": working.model_dump(mode="json"),
        "last_agent_action": final_action.model_dump(mode="json"),
        "recent_tool_results": observations[-3:],
        "active_skills": loaded,
        "discoverable_tools": sorted(exposed),
        "suggested_skills": suggested_skills or [],
        "missing_slots": critical_missing,
        "missing_fields": critical_missing,
        "current_stage_code": final_action.action,
        "runtime_metrics": {
            "decision_count": turn_step,
            "planner_call_count": planner_call_count,
            "model_call_count": model_call_count,
            "tool_call_count": len(tool_calls),
            "repair_count": repair_count,
            "max_prompt_chars": max_prompt_chars,
            "first_event_latency_ms": first_event_latency_ms,
            "total_latency_ms": round((monotonic() - turn_started) * 1000, 3),
        },
        "warnings": warnings,
    }
    return {
        "content": final_action.message or "", "task_spec": working.task,
        "working_context": working.model_dump(mode="json"), "workflow_state": workflow,
        "tool_calls": tool_calls, "events": events, "active_skills": loaded,
        "discoverable_tools": sorted(exposed), "warnings": warnings,
        "final_action": final_action.model_dump(mode="json"),
    }


def _select_skill_names(
    registry: Any,
    *,
    explicit: list[str],
    suggested: list[str],
    prepared: list[str],
    task: dict[str, Any],
    observations: list[dict[str, Any]],
) -> list[str]:
    available = {item.name for item in registry.list()}
    selected: list[str] = []

    def add(name: str) -> None:
        if name in available and name not in selected:
            selected.append(name)

    add("task_understanding")
    for name in [*explicit, *suggested, *prepared]:
        add(str(name))
    if task.get("material") and task.get("process_intent"):
        add("evidence_research")
        add("process_planning")
        add("parameter_recommendation")
        add("experiment_optimization")
    recent_tools = {str(item.get("tool_name") or "") for item in observations[-4:]}
    if "search_knowledge" in recent_tools:
        add("evidence_research")
        add("process_planning")
    if "recommend_process_parameters" in recent_tools:
        add("parameter_recommendation")
        add("experiment_optimization")
    return selected


def _fallback_blocking_action(fields: list[str]) -> AgentAction:
    questions = {
        "geometry.depth_mm": "矩形槽的目标深度（槽深）是多少，还是要求贯穿？",
    }
    selected = [questions[field] for field in fields if field in questions][:5]
    return AgentAction(
        action="ask_user",
        decision_summary="主模型不可用；仅追问任务抽取已确认的阻塞字段。",
        skills_used=["task_understanding"],
        message="\n".join(selected) or "请补充当前加工路线所必需的缺失信息。",
    )


def _skill_guidance(registry: Any, selected: list[str]) -> list[dict[str, Any]]:
    guidance: list[dict[str, Any]] = []
    for name in selected:
        item = registry.get(name)
        guidance.append({
            "name": item.name,
            "purpose": item.purpose,
            "method": list(item.method),
            "required_considerations": list(item.required_considerations),
            "recommended_tools": list(item.recommended_tools),
            "output_expectations": list(item.output_expectations),
            "prohibitions": list(item.prohibitions),
            "failure_handling": list(item.failure_handling),
        })
    return guidance


def _planner_context(working: WorkingContext) -> dict[str, Any]:
    value = working.model_dump(mode="json")
    value.pop("observations", None)
    value["documents"] = [
        {
            key: item.get(key)
            for key in ("document_id", "file_name", "path", "status", "content_type", "char_count")
            if item.get(key) is not None
        }
        for item in value.get("documents") or []
    ]
    return _compact_public_value(value, max_string=1600, max_list=8, max_depth=7)


def _planner_observations(
    observations: list[dict[str, Any]], turn_offset: int,
) -> list[dict[str, Any]]:
    prior = observations[max(0, turn_offset - 2):turn_offset]
    current = observations[turn_offset:]
    selected = [*prior, *current[-5:]]
    return [
        _compact_public_value(item, max_string=1200, max_list=6, max_depth=7)
        for item in selected
    ]


def _public_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return _compact_public_value(arguments, max_string=500, max_list=8, max_depth=6)


def _public_tool_observation(tool_name: str, envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    base: dict[str, Any] = {
        "status": envelope.get("status"),
        "summary": envelope.get("summary"),
        "warnings": envelope.get("warnings") or [],
        "error": envelope.get("error"),
        "meta": envelope.get("meta") or {},
    }
    if tool_name == "search_knowledge":
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        hits = list(data.get("hits") or result.get("hits") or [])
        base.update({
            "query": data.get("query"),
            "purpose": data.get("purpose"),
            "hit_count": len(hits),
            "evidence_status": result.get("evidence_status"),
            "retrieval_metadata": _compact_public_value(
                result.get("retrieval_metadata") or {}, max_string=300, max_list=5, max_depth=4,
            ),
            "hits": [
                _compact_public_value({
                    key: hit.get(key)
                    for key in (
                        "chunk_id", "paper_id", "title", "section_type", "authority_level",
                        "score", "rerank_score", "text", "content",
                    )
                    if hit.get(key) is not None
                }, max_string=360, max_list=3, max_depth=3)
                for hit in hits[:3]
                if isinstance(hit, dict)
            ],
        })
        return base
    if tool_name == "recommend_process_parameters":
        base.update({
            "selected_source": data.get("selected_source"),
            "source_type": data.get("source_type"),
            "authority_level": data.get("authority_level"),
            "evidence_level": data.get("evidence_level"),
            "data_support": data.get("data_support") or {},
            "uncertainty": data.get("uncertainty") or {},
            "allowed_for_trial": data.get("allowed_for_trial"),
            "allowed_for_formal_process": data.get("allowed_for_formal_process"),
            "internal_trace": data.get("internal_trace") or [],
            "process_parameters": data.get("process_parameters") or {},
            "strategy_parameters": data.get("strategy_parameters") or {},
            "limitations": data.get("limitations") or [],
        })
        return _compact_public_value(base, max_string=500, max_list=8, max_depth=6)
    if tool_name == "get_equipment_context":
        base.update({
            "equipment_profile_id": data.get("equipment_profile_id"),
            "profile_name": data.get("profile_name"),
            "revision_id": data.get("revision_id"),
            "fixed_conditions": data.get("fixed_conditions") or {},
            "tunable_capabilities": data.get("tunable_capabilities") or {},
            "missing_equipment_fields": data.get("missing_equipment_fields") or [],
        })
        return _compact_public_value(base, max_string=500, max_list=8, max_depth=6)
    base["data"] = data
    return _compact_public_value(base, max_string=600, max_list=8, max_depth=6)


def _compact_public_value(
    value: Any, *, max_string: int, max_list: int, max_depth: int,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return "<truncated>"
    if isinstance(value, dict):
        return {
            str(key): _compact_public_value(
                item, max_string=max_string, max_list=max_list,
                max_depth=max_depth, _depth=_depth + 1,
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        result = [
            _compact_public_value(
                item, max_string=max_string, max_list=max_list,
                max_depth=max_depth, _depth=_depth + 1,
            )
            for item in value[:max_list]
        ]
        if len(value) > max_list:
            result.append(f"<truncated {len(value) - max_list} items>")
        return result
    if isinstance(value, str) and len(value) > max_string:
        return value[:max_string] + f"…<truncated {len(value) - max_string} chars>"
    return value


def _rank_tool_schemas(items: list[dict[str, Any]], skills: Any, loaded: list[str]) -> list[dict[str, Any]]:
    recommended: set[str] = set()
    for name in loaded:
        recommended.update(skills.get(name).recommended_tools)
    return sorted(items, key=lambda item: (item["name"] not in recommended, item["name"]))


def _scoped_user_approval(message: str, message_id: str | None, tool: str,
                          arguments: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    operation = str(arguments.get("operation") or "")
    if (tool, operation) not in {("manage_trial", "start"), ("manage_process", "start")}:
        return False, None
    markers = ("确认开始", "确认执行", "可以开始", "开始试切", "开始正式加工", "同意开始")
    if not any(marker in message for marker in markers):
        return False, None
    observation = {
        "type": "UserApprovalObservation", "status": "success", "message_id": message_id,
        "scope": {"tool": tool, "operation": operation}, "source_text": message,
        "one_time": True, "observed_at": utc_now_iso(),
    }
    return True, observation


def _persist_context_nonblocking(
    session_id: str, message_id: str | None, working: WorkingContext, changed: list[str],
    events: list[dict[str, Any]], sink: Callable[[dict[str, Any]], None] | None, warnings: list[str],
    *, final_action: dict[str, Any] | None = None, decision_count: int | None = None,
) -> None:
    try:
        ContextPersistenceService().persist(
            session_id, working, changed_paths=changed, message_id=message_id,
            final_action=final_action, decision_count=decision_count,
        )
    except Exception as exc:  # noqa: BLE001 - persistence is a sidecar
        warning = f"Working Context 持久化失败：{type(exc).__name__}"
        if warning not in warnings:
            warnings.append(warning)
            _publish(events, sink, _safe_trace(
                session_id, message_id, "warning", "context_persistence", "上下文持久化警告",
                warning + "；内存上下文和前台任务继续。", "completed", {}, warnings,
            ))


def _safe_trace(
    session_id: str, message_id: str | None, event_type: str, stage: str,
    title: str, summary: str, status: str, payload: dict[str, Any], warnings: list[str],
    *, skill: str | None = None, tool: str | None = None,
) -> dict[str, Any]:
    try:
        return record_agent_trace_event(
            session_id=session_id, message_id=message_id, event_type=event_type, stage=stage,
            title=title, summary=summary, status=status, payload=payload, skill=skill, tool=tool,
            duration_ms=(float(payload["duration_ms"]) if isinstance(payload.get("duration_ms"), (int, float)) else None),
            cache_hit=(bool(payload.get("cache_hit")) if "cache_hit" in payload else None),
            attempt=(int(payload["attempt"]) if isinstance(payload.get("attempt"), int) else None),
            input_summary=payload.get("arguments"),
            output_summary=payload.get("observation"),
        )
    except Exception as exc:  # noqa: BLE001 - trace is observability only
        warning = f"Trace 写入失败：{type(exc).__name__}"
        if warning not in warnings:
            warnings.append(warning)
        return {
            "event_id": stable_id("ephemeral-event", session_id, message_id or "", event_type, utc_now_iso()),
            "event_type": event_type, "stage": stage, "title": title, "summary": summary,
            "status": status, "payload": payload, "skill": skill, "tool": tool,
        }


def _publish(events: list[dict[str, Any]], sink: Callable[[dict[str, Any]], None] | None,
             event: dict[str, Any]) -> None:
    events.append(event)
    if sink is not None:
        try:
            sink(event)
        except Exception:  # noqa: BLE001 - client disconnect cannot break domain work
            pass


def _critical_missing(task: dict[str, Any]) -> list[str]:
    geometry = task.get("geometry")
    if isinstance(geometry, dict) and geometry.get("feature_type") == "rectangular_groove" \
            and geometry.get("depth_mm") is None and not geometry.get("through"):
        return ["geometry.depth_mm"]
    return []


def _cached_observation(
    observations: list[dict[str, Any]], turn_offset: int, tool_name: str,
    arguments: dict[str, Any], cache_policy: str, equipment: dict[str, Any],
) -> dict[str, Any] | None:
    if cache_policy == "none":
        return None
    candidates = observations[turn_offset:] if cache_policy == "turn" else observations
    for item in reversed(candidates):
        if item.get("tool_name") != tool_name or item.get("status") not in {"success", "partial"}:
            continue
        meta = item.get("meta") or {}
        if meta.get("arguments") != arguments:
            continue
        if cache_policy == "equipment_revision":
            data = item.get("data") or {}
            if data.get("revision_id") != equipment.get("revision_id"):
                continue
        cached = deepcopy(item)
        cached.setdefault("meta", {}).update({"cache_hit": True, "duration_ms": 0.0})
        return cached
    return None


def _duplicate_turn_observation(
    observations: list[dict[str, Any]], turn_offset: int, tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    """Suppress exact duplicate execution even for side-effecting Tools."""
    for item in reversed(observations[turn_offset:]):
        if item.get("tool_name") != tool_name:
            continue
        if (item.get("meta") or {}).get("arguments") != arguments:
            continue
        duplicate = deepcopy(item)
        duplicate.setdefault("meta", {}).update({"cache_hit": True, "duration_ms": 0.0})
        return duplicate
    return None


def _exposed_tool_names(skills: Any, loaded: list[str]) -> set[str]:
    return exposed_tool_names(skills, loaded)


def _run_result_postprocess_hooks(
    payload: dict[str, Any], envelope: dict[str, Any], working: WorkingContext,
) -> None:
    """Extension point for governance workers; intentionally no foreground mutation."""
    return None
