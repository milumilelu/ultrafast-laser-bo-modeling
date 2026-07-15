from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.actions import AgentAction
from ultrafast_memory.agent_runtime.capability_discovery import exposed_tool_names
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.skill_registry import build_skill_registry
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


ABSOLUTE_EMERGENCY_DECISION_LIMIT = 30


def run_main_agent_turn(
    *, session_id: str, message: str, message_id: str | None, client: Any,
    suggested_skills: list[str] | None = None, active_skills: list[str] | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the single foreground control loop until a semantic terminal action."""
    registry = build_main_agent_tool_registry()
    executor = ToolExecutor(registry)
    skills = build_skill_registry()
    planner = MainAgentPlanner(client)
    state = get_session_state(session_id)
    working = load_working_context(state)
    if active_skills is not None:
        working.active_skills = list(dict.fromkeys(active_skills))
    loaded = [skills.get(name).name for name in working.active_skills]
    working.active_skills = list(dict.fromkeys(loaded))
    observations = working.observations
    turn_observation_offset = len(observations)
    tool_calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    final_action: AgentAction | None = None
    total_decisions = int(state.get("agent_decision_count") or 0)
    repeated_no_progress: dict[str, int] = {}
    recent_actions: list[dict[str, Any]] = []

    _publish(events, event_sink, _safe_trace(
        session_id, message_id, "agent_started", "main_agent", "主 Agent 已启动",
        "已读取当前 Working Context，开始推进任务。", "running", {}, warnings,
    ))

    turn_step = 0
    while True:
        turn_step += 1
        if turn_step > ABSOLUTE_EMERGENCY_DECISION_LIMIT:
            final_action = AgentAction(
                action="ask_user", decision_summary="检测到 probable planning loop，已触发内部失控保护。",
                message="当前规划未能继续产生有效进展。请确认是否调整目标或补充新的加工观察。",
            )
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "probable_agent_loop", "main_agent", "检测到规划循环",
                final_action.decision_summary, "completed", {"recent_actions": recent_actions[-8:]}, warnings,
            ))
            break

        exposed = exposed_tool_names(skills, loaded)
        tool_schemas = _rank_tool_schemas(registry.schemas_for_agent(exposed), skills, loaded)
        planning = _safe_trace(
            session_id, message_id, "agent_planning_started", "main_agent", "主 Agent 规划",
            "正在根据 Working Context 和最新观察规划下一动作。", "running", {"sequence": turn_step}, warnings,
        )
        _publish(events, event_sink, planning)
        action = planner.decide(
            message=message,
            working_context=working.model_dump(mode="json"),
            available_tools=tool_schemas,
            active_skills=loaded,
            recent_tool_results=observations,
            skill_catalog=skills.catalog_for_agent(),
            runtime_hints={"suggested_skills": suggested_skills or [], "router_is_hint_only": True},
        )
        final_action = action
        total_decisions += 1
        recent_actions.append({"action": action.action, "tool": action.tool_name, "arguments": action.arguments})
        _publish(events, event_sink, _safe_trace(
            session_id, message_id, "agent_decision", "main_agent", "主 Agent 决策",
            action.decision_summary, "completed",
            {"action": action.action, "sequence": turn_step,
             **({"validation_errors": action.error_details} if action.error_details else {})}, warnings,
            skill=action.skill_name, tool=action.tool_name,
        ))

        changed = working.apply(action.context_updates)
        if changed:
            _persist_context_nonblocking(
                session_id, message_id, working, changed, events, event_sink, warnings,
            )

        if action.action == "load_skill":
            descriptor = skills.load(str(action.skill_name))
            if descriptor["name"] not in loaded:
                loaded.append(descriptor["name"])
                working.active_skills = loaded
                changed.append("active_skills")
            observations.append({"action": "load_skill", "status": "success", "data": descriptor})
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "skill_loaded", "main_agent", f"Skill 已加载：{descriptor['name']}",
                "专业指导已加入规划上下文；Tool 可见性没有改变。", "completed", {}, warnings,
                skill=descriptor["name"],
            ))
            _persist_context_nonblocking(session_id, message_id, working, changed or ["observations"], events, event_sink, warnings)
            continue

        if action.action == "unload_skill":
            resolved = skills.get(str(action.skill_name)).name
            loaded = [name for name in loaded if name != resolved]
            working.active_skills = loaded
            observations.append({"action": "unload_skill", "status": "success", "data": {"name": resolved}})
            _publish(events, event_sink, _safe_trace(
                session_id, message_id, "skill_unloaded", "main_agent", f"Skill 已卸载：{resolved}",
                "专业指导已移除；Tool 可见性没有改变。", "completed", {}, warnings, skill=resolved,
            ))
            _persist_context_nonblocking(session_id, message_id, working, ["active_skills", "observations"], events, event_sink, warnings)
            continue

        if action.action != "call_tool":
            break

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
                {"arguments": action.arguments, "observation": cached}, warnings, tool=tool_name,
            ))
            if repeated_no_progress[duplicate_key] >= 3:
                final_action = AgentAction(
                    action="ask_user", decision_summary="同一 Tool 观察连续未产生上下文进展，判定 probable planning loop。",
                    message="现有工具结果已重复但没有产生新进展。请补充新的加工信息或调整目标。",
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
            contract.purpose, "running", {"arguments": action.arguments}, warnings, tool=tool_name,
        ))
        approved, approval_observation = _scoped_user_approval(message, message_id, tool_name, action.arguments)
        if approval_observation:
            observations.append(approval_observation)
        execution = executor.execute(
            tool_name, action.arguments,
            {
                "session_id": session_id, "message_id": message_id, "user_message": message,
                "working_context": working.model_dump(mode="json"), "task_spec": working.task,
                "equipment_snapshot": equipment, "human_approved": approved,
            },
        )
        envelope = execution.to_tool_result(tool_name)
        envelope.setdefault("meta", {}).update({
            "arguments": deepcopy(action.arguments), "cache_policy": contract.cache_policy, "cache_hit": False,
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
            "completed", {"tool_result": envelope}, warnings, tool=tool_name,
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
        "runtime_metrics": {"decision_count": turn_step, "tool_call_count": len(tool_calls)},
        "warnings": warnings,
    }
    return {
        "content": final_action.message or "", "task_spec": working.task,
        "working_context": working.model_dump(mode="json"), "workflow_state": workflow,
        "tool_calls": tool_calls, "events": events, "active_skills": loaded,
        "discoverable_tools": sorted(exposed), "warnings": warnings,
        "final_action": final_action.model_dump(mode="json"),
    }


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
