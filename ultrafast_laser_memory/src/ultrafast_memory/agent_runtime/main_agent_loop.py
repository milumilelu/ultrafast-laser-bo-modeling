from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_agent.task_intake import ClarificationContextService
from ultrafast_memory.agent_runtime.capability_discovery import exposed_tool_names
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.agent_runtime.skill_registry import build_skill_registry
from ultrafast_memory.agent_runtime.actions import AgentAction
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.process_workflow.business_state import BusinessStateController


_TOOL_STATE_PROJECTION = {
    "search_knowledge": "EVIDENCE_RETRIEVAL",
    "recommend_parameters_bo": "BO_RUNNING",
    "run_bo_iteration": "BO_RUNNING",
}


def run_main_agent_turn(
    *, session_id: str, message: str, message_id: str | None, client: Any,
    suggested_skills: list[str] | None = None, active_skills: list[str] | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run capability discovery until the Agent answers, asks, or stops making progress."""
    tools = build_main_agent_tool_registry()
    executor = ToolExecutor(tools)
    skills = build_skill_registry()
    controller = MainAgentPlanner(client)
    state = get_session_state(session_id)
    collected = dict(state.get("collected_slots") or {})
    task_spec = dict(collected.get("process_task_spec") or collected.get("task_spec") or {})
    workflow = dict(collected.get("process_workflow") or {})
    BusinessStateController.ensure(workflow)
    persisted_skills = active_skills if active_skills is not None else state.get("active_skills_json")
    loaded = [skills.get(name).name for name in (persisted_skills or [])]
    loaded = list(dict.fromkeys(loaded))
    observations = list(state.get("agent_observations_json") or [])[-40:]
    turn_observation_offset = len(observations)
    tool_calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    final_action: AgentAction | None = None
    total_decision_count = int(state.get("agent_decision_count") or 0)
    turn_step = 0
    seen_action_states: set[str] = set()

    while True:
        turn_step += 1
        exposed_names = exposed_tool_names(skills, loaded)
        tool_schemas = tools.schemas_for_agent(exposed_names)
        context = ClarificationContextService.build(
            get_session_state(session_id), loaded[0] if loaded else "task_understanding", task_spec,
        )
        planning_event = record_agent_trace_event(
            session_id=session_id,
            message_id=message_id,
            event_type="agent_planning_started",
            stage=str(workflow.get("substatus") or "INTAKE"),
            title="主 Agent 规划",
            summary="正在根据最新状态规划下一动作。",
            status="running",
            payload={"step": turn_step},
        )
        events.append(planning_event)
        _emit(event_sink, planning_event)
        action = controller.decide(
            message=message, task_spec=task_spec,
            business_state=str(workflow["business_state"]), context=context,
            available_tools=tool_schemas, active_skills=loaded,
            recent_tool_results=observations, skill_catalog=skills.catalog_for_agent(),
        )
        final_action = action
        total_decision_count += 1
        decision_event = _trace(session_id, message_id, workflow, action, turn_step)
        events.append(decision_event)
        _emit(event_sink, decision_event)

        action_state = _action_state_key(action, task_spec, loaded)
        if action_state in seen_action_states:
            final_action = AgentAction(
                action="ask_user",
                decision_summary="检测到未产生新状态的 Agent 动作循环，已停止空转。",
                message="当前能力调用未能产生新信息。请补充关键加工条件或调整任务目标。",
                provider=action.provider,
                model=action.model,
            )
            cycle_event = record_agent_trace_event(
                session_id=session_id,
                message_id=message_id,
                event_type="warning",
                stage=str(workflow.get("substatus") or "INTAKE"),
                title="Agent 循环已停止",
                summary=final_action.decision_summary,
                status="completed",
                payload={"step": turn_step, "reason": "repeated_action_without_state_change"},
            )
            events.append(cycle_event)
            _emit(event_sink, cycle_event)
            break
        seen_action_states.add(action_state)

        if action.action == "load_skill":
            assert action.skill_name is not None
            descriptor = skills.load(action.skill_name)
            if descriptor["name"] not in loaded:
                loaded.append(descriptor["name"])
            observations.append({"action": "load_skill", "status": "succeeded", "data": descriptor})
            skill_event = record_agent_trace_event(
                session_id=session_id,
                message_id=message_id,
                event_type="skill_loaded",
                stage=str(workflow.get("substatus") or "INTAKE"),
                title=f"Skill 已加载：{descriptor['name']}",
                summary="专业指导和推荐工具已加入下一次规划上下文。",
                skill=descriptor["name"],
                status="completed",
            )
            events.append(skill_event)
            _emit(event_sink, skill_event)
            continue
        if action.action == "unload_skill":
            assert action.skill_name is not None
            resolved = skills.get(action.skill_name).name
            loaded = [name for name in loaded if name != resolved]
            observations.append({"action": "unload_skill", "status": "succeeded", "data": {"name": resolved}})
            skill_event = record_agent_trace_event(
                session_id=session_id,
                message_id=message_id,
                event_type="skill_unloaded",
                stage=str(workflow.get("substatus") or "INTAKE"),
                title=f"Skill 已卸载：{resolved}",
                summary="该专业指导已从下一次规划上下文移除。",
                skill=resolved,
                status="completed",
            )
            events.append(skill_event)
            _emit(event_sink, skill_event)
            continue
        if action.action != "call_tool":
            break

        assert action.tool_name is not None
        equipment = build_machine_bounds()
        contract = tools.get(action.tool_name)
        cached_envelope = _cached_observation(
            observations,
            turn_observation_offset,
            action.tool_name,
            action.arguments,
            contract.cache_policy,
            equipment,
        )
        started_event = record_agent_trace_event(
            session_id=session_id, message_id=message_id,
            event_type="tool_cache_hit" if cached_envelope is not None else "tool_call_started",
            stage=str(workflow.get("substatus") or "INTAKE"),
            title=f"{action.tool_name} 命中缓存" if cached_envelope is not None else f"调用 {action.tool_name}",
            summary="复用未变更设备版本或本轮已有观察。" if cached_envelope is not None else contract.purpose,
            skill=loaded[0] if loaded else None,
            tool=action.tool_name, status="running", payload={"arguments": action.arguments},
        )
        events.append(started_event)
        _emit(event_sink, started_event)
        if cached_envelope is not None:
            envelope = cached_envelope
            execution_status = str(envelope.get("status") or "succeeded")
            execution_error = str((envelope.get("error") or {}).get("message") or "")
        else:
            execution = executor.execute(
                action.tool_name, action.arguments,
                {"session_id": session_id, "message_id": message_id, "user_message": message,
                 "clarification_context": context.model_dump(mode="json"), "task_spec": task_spec,
                 "equipment_snapshot": equipment, "human_approved": False},
            )
            envelope = execution.to_tool_result(action.tool_name)
            envelope.setdefault("meta", {}).update({
                "arguments": deepcopy(action.arguments),
                "cache_policy": contract.cache_policy,
                "cache_hit": False,
            })
            execution_status = execution.status
            execution_error = execution.error_message or ""
        call = {"step": turn_step, "tool_name": action.tool_name, "arguments": action.arguments,
                "result": envelope, "status": execution_status,
                "cache_hit": cached_envelope is not None}
        tool_calls.append(call)
        observations.append(envelope)
        workflow["last_tool_result"] = envelope
        data = envelope.get("data")
        completed_event = record_agent_trace_event(
            session_id=session_id, message_id=message_id,
            event_type="tool_completed" if execution_status == "succeeded" else "tool_failed",
            stage=str(workflow.get("substatus") or "INTAKE"), title=f"{action.tool_name} 执行结果",
            summary=("已复用缓存观察。" if cached_envelope is not None else "工具执行成功。")
            if execution_status == "succeeded" else execution_error or "工具未执行。",
            skill=loaded[0] if loaded else None, tool=action.tool_name, status="completed",
            payload={"tool_result": envelope, **(data if isinstance(data, dict) else {})},
        )
        events.append(completed_event)
        _emit(event_sink, completed_event)
        if action.tool_name == "update_task_context" and isinstance(data, dict) and data.get("task_spec") is not None:
            task_spec = dict(data["task_spec"])
            update_complete = not data.get("rejected") and not data.get("conflicts")
            if update_complete and not _message_requests_continuation(message):
                critical = _geometry_critical_missing(task_spec)
                if critical:
                    final_action = AgentAction(
                        action="ask_user",
                        decision_summary="槽深会显著改变加工路线和参数空间，必须先确认。",
                        message=_critical_geometry_question(task_spec),
                        provider=action.provider,
                        model=action.model,
                    )
                else:
                    final_action = AgentAction(
                        action="final_answer",
                        decision_summary="当前消息中的全部明确任务事实已一次性校验并保存。",
                        message="已保存本轮明确提供的任务信息；未生成任何未经验证的工艺参数。",
                        provider=action.provider,
                        model=action.model,
                    )
                stopped_event = record_agent_trace_event(
                    session_id=session_id,
                    message_id=message_id,
                    event_type="decision",
                    stage=str(workflow.get("substatus") or "INTAKE"),
                    title="任务事实写入完成",
                    summary=final_action.decision_summary,
                    status="completed",
                    payload={"action": final_action.action, "reason": "task_update_complete"},
                )
                events.append(stopped_event)
                _emit(event_sink, stopped_event)
                break
        projected = _TOOL_STATE_PROJECTION.get(action.tool_name)
        if projected:
            BusinessStateController.transition(workflow, projected)

    if final_action is None:
        raise RuntimeError("main agent produced no action")
    content = final_action.message or ""
    exposed_names = exposed_tool_names(skills, loaded)
    critical_missing = _remaining_missing_fields(workflow, task_spec)
    workflow["missing_fields"] = critical_missing
    workflow.update({
        "runtime_mode": "capability_discovery",
        "task_spec": task_spec, "last_agent_action": final_action.model_dump(mode="json"),
        "recent_tool_results": observations[-3:], "active_skills": loaded,
        "discoverable_tools": sorted(exposed_names), "suggested_skills": suggested_skills or [],
        "missing_slots": critical_missing,
        "current_stage_code": final_action.action,
        "runtime_metrics": {
            "decision_count": turn_step,
            "tool_call_count": len(tool_calls),
        },
    })
    latest = get_session_state(session_id)
    latest_collected = dict(latest.get("collected_slots") or {})
    latest_collected.update({"task_spec": task_spec, "process_task_spec": task_spec,
                             "process_workflow": workflow, "main_agent_tool_history": tool_calls[-20:]})
    update_session_state(session_id, {
        "collected_slots": latest_collected, "active_skills_json": loaded,
        "agent_observations_json": observations[-100:], "agent_decision_count": total_decision_count,
        "last_agent_action_json": final_action.model_dump(mode="json"),
    })
    return {"content": content, "task_spec": task_spec, "workflow_state": workflow,
            "tool_calls": tool_calls, "events": events,
            "active_skills": loaded, "discoverable_tools": sorted(exposed_names),
            "final_action": final_action.model_dump(mode="json")}


def _exposed_tool_names(skills: Any, loaded: list[str]) -> set[str]:
    """Compatibility alias for callers; discovery logic has one implementation."""
    return exposed_tool_names(skills, loaded)


def _trace(session_id: str, message_id: str | None, workflow: dict[str, Any],
           action: AgentAction, step: int) -> dict[str, Any]:
    return record_agent_trace_event(
        session_id=session_id, message_id=message_id, event_type="agent_decision",
        stage=str(workflow.get("substatus") or "INTAKE"), title="主 Agent 决策",
        summary=action.decision_summary, skill=action.skill_name, tool=action.tool_name,
        status="completed", payload={
            "action": action.action,
            "step": step,
            **({"validation_errors": action.error_details} if action.error_details else {}),
        },
    )


def _action_state_key(action: AgentAction, task_spec: dict[str, Any], loaded: list[str]) -> str:
    return json.dumps(
        {
            "action": action.action,
            "skill_name": action.skill_name,
            "tool_name": action.tool_name,
            "arguments": action.arguments,
            "task_spec": task_spec,
            "loaded_skills": loaded,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _emit(sink: Callable[[dict[str, Any]], None] | None, event: dict[str, Any]) -> None:
    if sink is None:
        return
    try:
        sink(event)
    except Exception:  # noqa: BLE001 - observability must not break domain execution
        return


def _remaining_missing_fields(workflow: dict[str, Any], task_spec: dict[str, Any]) -> list[str]:
    existing = [
        str(field) for field in workflow.get("missing_fields") or []
        if _lookup(task_spec, str(field)) is None
    ]
    existing.extend(_geometry_critical_missing(task_spec))
    return list(dict.fromkeys(existing))


def _geometry_critical_missing(task_spec: dict[str, Any]) -> list[str]:
    geometry = task_spec.get("geometry")
    if (
        isinstance(geometry, dict)
        and geometry.get("feature_type") in {"groove", "rectangular_groove"}
        and geometry.get("depth_mm") is None
        and not geometry.get("through")
    ):
        return ["geometry.depth_mm"]
    return []


def _message_requests_continuation(message: str) -> bool:
    return any(marker in message for marker in (
        "推荐", "参数", "方案", "检索", "查询", "查找", "优化", "实验计划", "报告",
    ))


def _critical_geometry_question(task_spec: dict[str, Any]) -> str:
    geometry = task_spec.get("geometry") or {}
    dimensions = geometry.get("dimensions") or {}
    material = str(task_spec.get("material") or "当前材料")
    length = dimensions.get("length_mm")
    width = dimensions.get("width_mm")
    size = (
        f"{length:g} mm × {width:g} mm "
        if isinstance(length, (int, float)) and isinstance(width, (int, float))
        else ""
    )
    return (
        f"已保存材料（{material}）、槽加工意图和 {size}矩形槽槽口尺寸。"
        "请提供目标深度（槽深），或说明是否贯穿。"
    )


def _lookup(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _cached_observation(
    observations: list[dict[str, Any]],
    turn_offset: int,
    tool_name: str,
    arguments: dict[str, Any],
    cache_policy: str,
    equipment: dict[str, Any],
) -> dict[str, Any] | None:
    if cache_policy == "none":
        return None
    candidates = observations[turn_offset:] if cache_policy == "turn" else observations
    for item in reversed(candidates):
        if item.get("tool_name") != tool_name or item.get("status") != "succeeded":
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
