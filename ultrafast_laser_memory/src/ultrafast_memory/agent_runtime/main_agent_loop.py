from __future__ import annotations

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
    max_steps: int = 8,
) -> dict[str, Any]:
    """Run capability discovery and LLM→action→observation cycles without an FSM gate."""
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
    tool_calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    final_action: AgentAction | None = None
    total_step_count = int(state.get("agent_step_count") or 0)

    for turn_step in range(1, max_steps + 1):
        exposed_names = exposed_tool_names(skills, loaded)
        tool_schemas = tools.schemas_for_agent(exposed_names)
        context = ClarificationContextService.build(
            get_session_state(session_id), loaded[0] if loaded else "task_understanding", task_spec,
        )
        action = controller.decide(
            message=message, task_spec=task_spec,
            business_state=str(workflow["business_state"]), context=context,
            available_tools=tool_schemas, active_skills=loaded,
            recent_tool_results=observations, skill_catalog=skills.catalog_for_agent(),
        )
        final_action = action
        total_step_count += 1
        events.append(_trace(session_id, message_id, workflow, action, turn_step))

        if action.action == "load_skill":
            assert action.skill_name is not None
            descriptor = skills.load(action.skill_name)
            if descriptor["name"] not in loaded:
                loaded.append(descriptor["name"])
            observations.append({"action": "load_skill", "status": "succeeded", "data": descriptor})
            continue
        if action.action == "unload_skill":
            assert action.skill_name is not None
            resolved = skills.get(action.skill_name).name
            loaded = [name for name in loaded if name != resolved]
            observations.append({"action": "unload_skill", "status": "succeeded", "data": {"name": resolved}})
            continue
        if action.action != "call_tool":
            break

        assert action.tool_name is not None
        if tool_calls and tool_calls[-1]["tool_name"] == action.tool_name and tool_calls[-1]["arguments"] == action.arguments:
            final_action = AgentAction(
                action="final_answer", decision_summary="检测到无新观察的重复工具调用，停止循环。",
                message="已保存本轮明确提供的信息和工具观察。", provider=action.provider, model=action.model,
            )
            break
        equipment = build_machine_bounds()
        events.append(record_agent_trace_event(
            session_id=session_id, message_id=message_id, event_type="tool_call_started",
            stage=str(workflow.get("substatus") or "INTAKE"), title=f"调用 {action.tool_name}",
            summary=tools.get(action.tool_name).purpose, skill=loaded[0] if loaded else None,
            tool=action.tool_name, status="running", payload={"arguments": action.arguments},
        ))
        execution = executor.execute(
            action.tool_name, action.arguments,
            {"session_id": session_id, "message_id": message_id, "user_message": message,
             "clarification_context": context.model_dump(mode="json"), "task_spec": task_spec,
             "equipment_snapshot": equipment, "human_approved": False},
        )
        envelope = execution.to_tool_result(action.tool_name)
        call = {"step": turn_step, "tool_name": action.tool_name, "arguments": action.arguments,
                "result": envelope, "status": execution.status}
        tool_calls.append(call)
        observations.append(envelope)
        workflow["last_tool_result"] = envelope
        data = envelope.get("data")
        events.append(record_agent_trace_event(
            session_id=session_id, message_id=message_id,
            event_type="tool_completed" if execution.status == "succeeded" else "tool_failed",
            stage=str(workflow.get("substatus") or "INTAKE"), title=f"{action.tool_name} 执行结果",
            summary="工具执行成功。" if execution.status == "succeeded" else execution.error_message or "工具未执行。",
            skill=loaded[0] if loaded else None, tool=action.tool_name, status="completed",
            payload={"tool_result": envelope, **(data if isinstance(data, dict) else {})},
        ))
        if action.tool_name == "update_task_context" and isinstance(data, dict) and data.get("task_spec") is not None:
            task_spec = dict(data["task_spec"])
            if not data.get("applied") and data.get("unchanged") and not data.get("conflicts"):
                final_action = AgentAction(
                    action="final_answer",
                    decision_summary="任务事实已存在且本轮没有产生新变更，停止重复写入。",
                    message="已记录材料、加工动作和尺寸信息；本轮未生成未经验证的工艺参数。",
                    provider=action.provider,
                    model=action.model,
                )
                events.append(record_agent_trace_event(
                    session_id=session_id,
                    message_id=message_id,
                    event_type="decision",
                    stage=str(workflow.get("substatus") or "INTAKE"),
                    title="停止重复状态写入",
                    summary=final_action.decision_summary,
                    status="completed",
                    payload={"action": "final_answer", "reason": "no_new_task_spec_change"},
                ))
                break
        projected = _TOOL_STATE_PROJECTION.get(action.tool_name)
        if projected:
            BusinessStateController.transition(workflow, projected)

    if final_action is None:
        raise RuntimeError("main agent produced no action")
    content = (
        "已达到本轮 Agent 步数上限；状态和观察均已保存，可在下一轮继续。"
        if final_action.action in {"call_tool", "load_skill", "unload_skill"}
        else final_action.message or ""
    )
    exposed_names = exposed_tool_names(skills, loaded)
    workflow.update({
        "runtime_mode": "capability_discovery",
        "task_spec": task_spec, "last_agent_action": final_action.model_dump(mode="json"),
        "recent_tool_results": observations[-3:], "active_skills": loaded,
        "discoverable_tools": sorted(exposed_names), "suggested_skills": suggested_skills or [],
        "missing_slots": list(workflow.get("missing_fields") or []),
        "current_stage_code": final_action.action,
    })
    latest = get_session_state(session_id)
    latest_collected = dict(latest.get("collected_slots") or {})
    latest_collected.update({"task_spec": task_spec, "process_task_spec": task_spec,
                             "process_workflow": workflow, "main_agent_tool_history": tool_calls[-20:]})
    update_session_state(session_id, {
        "collected_slots": latest_collected, "active_skills_json": loaded,
        "agent_observations_json": observations[-100:], "agent_step_count": total_step_count,
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
