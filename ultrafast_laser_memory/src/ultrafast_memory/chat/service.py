from __future__ import annotations

from collections.abc import Iterator

from ultrafast_agent.observability import DebugTraceRenderer, TUIRenderer
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.chat.prompt_builder import build_system_prompt
from ultrafast_memory.chat.legacy_status_parser import LegacyTaskSpecAdapter
from ultrafast_memory.chat.router.debug_commands import handle_debug_command
from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.chat.schemas import ChatRequest, ChatResponse
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.chat.session_store import (
    create_session,
    get_recent_messages,
    save_message,
    save_skill_trace,
    session_exists,
)
from ultrafast_memory.chat.legacy_projection_adapter import LegacyWorkflowProjectionAdapter
from ultrafast_memory.core.config import load_config
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge
from ultrafast_memory.knowledge_review.review_queue import get_review_task
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.llm.openai_compatible import LLMProviderError
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn


def handle_chat(request: ChatRequest) -> ChatResponse:
    session_id = _ensure_session(request)

    user_message = save_message(session_id, "user", request.message, {"mode": request.mode})
    state = get_session_state(session_id)

    mode_command = _handle_display_mode_command(request.message, session_id)
    if mode_command:
        save_message(session_id, "assistant", mode_command["assistant_message"], {"display_mode": mode_command.get("display_mode")})
        return _build_command_chat_response(
            session_id,
            mode_command["assistant_message"],
            [{"step": "display_mode", "status": "success", "mode": mode_command.get("display_mode")}],
        )

    bootstrap_command = _handle_bootstrap_chat_command(request.message, session_id, state)
    if bootstrap_command:
        save_message(session_id, "assistant", bootstrap_command["assistant_message"], {"knowledge_bootstrap": bootstrap_command.get("knowledge_bootstrap")})
        return _build_legacy_chat_response(
            session_id=session_id,
            assistant_message=bootstrap_command["assistant_message"],
            message=request.message,
            message_id=user_message["message_id"],
            selected_skill=bootstrap_command.get("selected_skill"),
            route_plan=bootstrap_command.get("route_plan"),
            evidence_gap=bootstrap_command.get("evidence_gap"),
            knowledge_bootstrap=bootstrap_command.get("knowledge_bootstrap"),
            audit_trace=bootstrap_command.get("audit_trace", []),
            stage=bootstrap_command.get("workflow_stage"),
            status=bootstrap_command.get("workflow_status"),
        )

    permission_result = _handle_bootstrap_permission_reply(request.message, session_id, state)
    if permission_result:
        save_message(session_id, "assistant", permission_result["assistant_message"], {"knowledge_bootstrap": permission_result.get("knowledge_bootstrap")})
        return _build_legacy_chat_response(
            session_id=session_id,
            assistant_message=permission_result["assistant_message"],
            message=request.message,
            message_id=user_message["message_id"],
            selected_skill=permission_result.get("selected_skill"),
            route_plan=permission_result.get("route_plan"),
            evidence_gap=permission_result.get("evidence_gap"),
            knowledge_bootstrap=permission_result.get("knowledge_bootstrap"),
            audit_trace=permission_result.get("audit_trace", []),
            stage=permission_result.get("workflow_stage"),
            status=permission_result.get("workflow_status"),
        )

    continuation_guard = _handle_review_guard(request.message, session_id, state)
    if continuation_guard:
        save_message(session_id, "assistant", continuation_guard["assistant_message"], {"knowledge_bootstrap": continuation_guard.get("knowledge_bootstrap")})
        return _build_legacy_chat_response(
            session_id=session_id,
            assistant_message=continuation_guard["assistant_message"],
            message=request.message,
            message_id=user_message["message_id"],
            selected_skill=continuation_guard.get("selected_skill"),
            route_plan=continuation_guard.get("route_plan"),
            knowledge_bootstrap=continuation_guard.get("knowledge_bootstrap"),
            audit_trace=continuation_guard.get("audit_trace", []),
            stage=continuation_guard.get("workflow_stage"),
            status=continuation_guard.get("workflow_status"),
        )

    debug_command = handle_debug_command(request.message, session_id)
    if debug_command and not request.message.strip().startswith("/skill "):
        assistant_content = _debug_response(debug_command)
        save_message(session_id, "assistant", assistant_content, {"debug_command": True})
        return _build_command_chat_response(
            session_id,
            assistant_content,
            [{"step": "debug_command", "status": "success"}],
        )

    route_plan = None
    selected_skill = None
    audit_trace: list[dict] = []
    if request.use_skills:
        route_plan = route_message(request.message, session_id, user_message["message_id"])
        selected_skill = route_plan.primary_skill
        route_event = _record_route_decision_trace(
            session_id, user_message["message_id"], request.message, route_plan
        )
        save_skill_trace(
            session_id,
            user_message["message_id"],
            {
                "selected_skill": selected_skill,
                "confidence": route_plan.confidence,
                "reason": route_plan.reason,
            },
        )
        audit_trace.append(
            {
                "step": "hybrid_router",
                "status": "success",
                "selected_skill": selected_skill,
                "route_source": route_plan.route_source,
            }
        )
        suggested_skills = list(dict.fromkeys([
            route_plan.primary_skill,
            *route_plan.secondary_skills,
        ]))
        agent_result = run_main_agent_turn(
            session_id=session_id,
            message=request.message,
            message_id=user_message["message_id"],
            client=create_llm_client(get_llm_config()),
            suggested_skills=suggested_skills,
        )
        audit_trace.append({
            "step": "main_agent_loop",
            "status": "success",
            "tool_call_count": len(agent_result["tool_calls"]),
        })
        assistant_content = agent_result["content"]
        save_message(
            session_id,
            "assistant",
            assistant_content,
            {
                "selected_skill": selected_skill,
                "active_skills": agent_result["active_skills"],
                "suggested_skills": suggested_skills,
                "route_plan": route_plan.model_dump(mode="json"),
                "tool_calls": agent_result["tool_calls"],
            },
        )
        return _build_agent_chat_response(
            session_id=session_id,
            assistant_message=assistant_content,
            selected_skill=selected_skill,
            route_plan=route_plan.model_dump(mode="json"),
            route_event=route_event,
            agent_result=agent_result,
            audit_trace=audit_trace,
        )

    history = get_recent_messages(session_id, limit=20)
    messages = [{"role": "system", "content": build_system_prompt(selected_skill)}] + history
    cfg = get_llm_config()
    client = create_llm_client(cfg)
    record_agent_trace_event(
        session_id=session_id,
        message_id=user_message["message_id"],
        event_type="tool_call",
        stage="llm_chat",
        title="调用语言模型",
        summary="正在生成面向用户的回复。",
        skill=selected_skill,
        tool="llm_adapter",
        input_summary=f"history_messages={len(history)}; model={cfg.get('model')}",
        status="running",
    )
    try:
        result = client.chat(messages, temperature=0.2)
        llm_status = "success"
    except Exception as exc:
        result = {
            "content": _llm_fallback_message(),
            "provider": "fallback_template",
            "model": "deterministic-safe-fallback",
        }
        llm_status = "fallback"
        record_agent_trace_event(
            session_id=session_id,
            message_id=user_message["message_id"],
            event_type="fallback",
            stage="llm_chat",
            title="语言模型降级",
            summary=f"{_safe_llm_error(exc)}；已使用不含工艺参数的安全模板。",
            skill=selected_skill,
            tool="llm_adapter",
            status="completed",
        )
    assistant_content = result.get("content") or ""
    save_message(
        session_id,
        "assistant",
        assistant_content,
        {
            "provider": result.get("provider"),
            "model": result.get("model"),
            "selected_skill": selected_skill,
            "route_plan": route_plan.model_dump(mode="json") if route_plan else None,
        },
    )
    audit_trace.append(
        {
            "step": "llm_chat",
            "status": llm_status,
            "provider": result.get("provider"),
        }
    )
    record_agent_trace_event(
        session_id=session_id,
        message_id=user_message["message_id"],
        event_type="tool_result",
        stage="llm_chat",
        title="语言模型返回",
        summary="已生成回复文本。",
        skill=selected_skill,
        tool="llm_adapter",
        output_summary=f"provider={result.get('provider')}; model={result.get('model')}; chars={len(assistant_content)}",
        status="completed",
    )
    return _build_legacy_chat_response(
        session_id=session_id,
        assistant_message=assistant_content,
        message=request.message,
        message_id=user_message["message_id"],
        selected_skill=selected_skill,
        route_plan=route_plan.model_dump(mode="json") if route_plan else None,
        route_plan_obj=route_plan,
        tool_calls=[],
        audit_trace=audit_trace,
    )


def handle_chat_stream_ndjson(request: ChatRequest) -> Iterator[dict]:
    # One application execution path: streaming is only a renderer over the
    # same ChatResponse produced by the non-streaming workflow.
    response = handle_chat(request.model_copy(update={"stream": False}))
    route = response.route_plan or {}
    yield {
        "type": "meta", "session_id": response.session_id,
        "provider": "workflow",
        "model": "main-agent-loop-v1" if route else "shared-chat-workflow-v1",
    }
    if response.progress:
        yield _progress_event(response.progress)
    thinking_event_ids = {
        item["event_id"] for item in response.thinking_status if item.get("event_id")
    }
    for item in response.execution_trace:
        if item.get("event_id") in thinking_event_ids:
            yield _thinking_event(item)
        else:
            yield _agent_trace_event(item)
    if route:
        yield {
            "type": "route", "primary_skill": route.get("primary_skill"),
            "secondary_skills": route.get("secondary_skills") or [],
            "confidence": route.get("confidence"), "route_source": route.get("route_source"),
        }
        yield {"type": "trace", "step": "hybrid_router", "status": "success", "selected_skill": route.get("primary_skill")}
    for item in response.audit_trace:
        if item.get("status") == "fallback":
            yield {
                "type": "warning", "event_type": "fallback", "stage": item.get("step", "llm_chat"),
                "status": "completed", "summary": item.get("detail") or "已使用安全降级模板。",
            }
    if response.workflow_state:
        workflow_state = dict(response.workflow_state)
        # Stream v3 retained the localized display field; the stable machine
        # code remains available separately for new clients.
        if workflow_state.get("current_stage_label"):
            workflow_state["current_stage"] = workflow_state["current_stage_label"]
        yield {"type": "workflow_state", **workflow_state}
    yield {"type": "delta", "content": response.assistant_message}
    yield {"type": "done"}
    return
def _llm_fallback_message() -> str:
    return (
        "语言模型当前不可用。已保留任务、设备、证据和工作流状态；"
        "请稍后重试。离线降级不会生成未经验证的工艺参数。"
    )


def _safe_llm_error(exc: Exception) -> str:
    if isinstance(exc, LLMProviderError):
        return str(exc)
    return type(exc).__name__


def _title_from_message(message: str) -> str:
    title = " ".join(message.strip().split())
    if not title:
        return "Untitled chat"
    return title[:48]


def _ensure_session(request: ChatRequest) -> str:
    if request.session_id and session_exists(request.session_id):
        return request.session_id
    session = create_session(title=_title_from_message(request.message), mode=request.mode)
    return session["session_id"]


def _debug_response(debug_command: dict) -> str:
    import json

    safe = {key: value for key, value in debug_command.items() if key != "handled"}
    return json.dumps(safe, ensure_ascii=False, indent=2)


def _record_route_decision_trace(
    session_id: str,
    message_id: str | None,
    message: str,
    route_plan,
    progress: int | float | None = None,
) -> dict:
    return record_agent_trace_event(
        session_id=session_id,
        message_id=message_id,
        event_type="decision",
        stage=route_plan.workflow_stage,
        title="路由决策",
        summary=route_plan.reason,
        progress=progress,
        skill=route_plan.primary_skill,
        tool="route_planner",
        input_summary=message[:240],
        output_summary=f"primary_skill={route_plan.primary_skill}; route_source={route_plan.route_source}",
        status="completed",
    )


def _handle_display_mode_command(message: str, session_id: str) -> dict | None:
    text = message.strip().lower()
    if not text.startswith("/mode "):
        return None
    mode = text[len("/mode ") :].strip()
    if mode not in {"normal", "research", "debug"}:
        return {"assistant_message": "无效显示模式。可选：normal、research、debug。", "display_mode": None}
    update_session_state(session_id, {"collected_slots": {"display_mode": mode}})
    return {"assistant_message": f"显示模式已切换为：{mode}。", "display_mode": mode}


def _build_command_chat_response(
    session_id: str,
    assistant_message: str,
    audit_trace: list[dict],
) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        assistant_message=assistant_message,
        audit_trace=audit_trace,
    )


def _build_agent_chat_response(
    *,
    session_id: str,
    assistant_message: str,
    selected_skill: str | None,
    route_plan: dict,
    route_event: dict,
    agent_result: dict,
    audit_trace: list[dict],
) -> ChatResponse:
    """Project normal chat exclusively from actions and tool observations that occurred."""
    final_action = dict(agent_result.get("final_action") or {})
    action = str(final_action.get("action") or "unknown")
    waiting_user = action == "ask_user"
    bounded = action in {"call_tool", "load_skill", "unload_skill"}
    status = "waiting_user" if waiting_user else "step_limit" if bounded else "completed"
    progress = {
        "workflow_type": "main_agent",
        "current_stage": action,
        "progress_percent": None,
        "status": status,
        "message": final_action.get("decision_summary") or "主 Agent 已完成本轮动作。",
        "completed_steps": [],
        "pending_steps": [],
    }
    events = [route_event, *(agent_result.get("events") or [])]
    visible_trace = _filter_public_trace(session_id, events)
    reasoning = [
        item for item in visible_trace
        if item.get("event_type") in {"decision", "agent_decision"}
    ]
    if _public_trace_mode(session_id) == "off":
        reasoning = []
    workflow_state = dict(agent_result.get("workflow_state") or {})
    session = get_session_state(session_id)
    collected = dict(session.get("collected_slots") or {})
    workflow_state.update({
        "runtime_mode": "capability_discovery",
        "current_stage_code": action,
        "task_spec": dict(agent_result.get("task_spec") or {}),
        "active_skills": list(agent_result.get("active_skills") or []),
        "discoverable_tools": list(agent_result.get("discoverable_tools") or []),
        "agent_action": final_action,
        "missing_slots": list(workflow_state.get("missing_fields") or []),
        "clarification_round": int(workflow_state.get("clarification_round") or 0),
        "field_provenance": dict(collected.get("process_task_field_provenance") or {}),
        "revision_history": list(collected.get("process_task_revision_history") or []),
    })
    equipment_call = next((
        call for call in reversed(agent_result.get("tool_calls") or [])
        if call.get("tool_name") == "get_equipment_context"
        and (call.get("result") or {}).get("status") == "succeeded"
    ), None)
    if equipment_call:
        equipment = dict((equipment_call.get("result") or {}).get("data") or {})
        workflow_state["equipment_profile_used"] = equipment
        workflow_state["machine_bounds"] = dict(equipment.get("machine_bounds") or {})
    next_action = {
        "action_type": "provide_clarification" if waiting_user else "continue_agent" if bounded else "answer_complete",
        "required_fields": list(workflow_state.get("missing_slots") or []),
        "blocking": waiting_user,
    }
    workflow_state["next_required_action"] = next_action
    overview = [
        {
            "step": item.get("title") or item.get("event_type") or "agent_event",
            "status": item.get("status") or "completed",
        }
        for item in visible_trace
    ]
    return ChatResponse(
        session_id=session_id,
        assistant_message=assistant_message,
        selected_skill=selected_skill,
        route_plan=route_plan,
        progress=progress,
        thinking_status=reasoning,
        workflow_state=workflow_state,
        execution_trace=visible_trace,
        tool_calls=agent_result.get("tool_calls") or [],
        audit_trace=audit_trace,
        workflow_overview=overview,
        current_stage=action,
        current_stage_code=action,
        completed_stages=[],
        pending_stages=[],
        blocked_stages=[],
        next_required_action=next_action,
        skill_trace=[item for item in visible_trace if item.get("skill")],
        tool_trace=[item for item in visible_trace if item.get("tool")],
        reasoning_trace=reasoning,
    )


def _build_legacy_chat_response(
    session_id: str,
    assistant_message: str,
    message: str,
    message_id: str | None = None,
    selected_skill: str | None = None,
    route_plan: dict | None = None,
    route_plan_obj=None,
    evidence_gap: dict | None = None,
    knowledge_bootstrap: dict | None = None,
    tool_calls: list | None = None,
    audit_trace: list[dict] | None = None,
    stage: str | None = None,
    status: str | None = None,
    rag_evidence: dict | None = None,
    citations: list[dict] | None = None,
) -> ChatResponse:
    workflow_type = getattr(route_plan_obj, "primary_skill", None) or selected_skill or "task_intake"
    session = get_session_state(session_id)
    collected = dict(session.get("collected_slots") or {})
    current_task_spec = dict(collected.get("task_spec") or {})
    candidate = LegacyTaskSpecAdapter.adapt(message, workflow_type)
    # Legacy projection may enrich missing display fields, but it must never
    # overwrite canonical facts without an explicit correction tool call.
    task_spec = {**candidate, **current_task_spec}
    collected["task_spec"] = task_spec
    update_session_state(session_id, {"collected_slots": collected})
    artifacts = LegacyWorkflowProjectionAdapter.build_and_persist(
        session_id=session_id,
        message_id=message_id,
        task_spec=task_spec,
        route_plan=route_plan_obj,
        stage=stage,
        status=status,
    )
    assistant_message = _clarification_limit_message(artifacts) or assistant_message
    process_workflow = dict(collected.get("process_workflow") or {})
    artifacts["workflow_state"].update({
        "current_stage_code": artifacts["workflow_state"].get("substatus"),
        "field_provenance": collected.get("process_task_field_provenance") or {},
        "revision_history": collected.get("process_task_revision_history") or [],
        "active_skills": session.get("active_skills_json") or [],
        "discoverable_tools": process_workflow.get("discoverable_tools") or [],
        "agent_action": process_workflow.get("last_agent_action"),
        "last_tool_result": process_workflow.get("last_tool_result"),
    })
    completed = artifacts["progress"].get("completed_steps") or []
    pending = artifacts["progress"].get("pending_steps") or []
    overview = ([{"step": step, "status": "completed"} for step in completed] +
                [{"step": step, "status": "pending"} for step in pending])
    missing = artifacts["workflow_state"].get("missing_slots") or []
    next_action = {
        "action_type": "submit_required_fields" if missing else "continue_workflow",
        "required_fields": missing,
        "blocking": bool(missing),
    }
    artifacts["workflow_state"]["next_required_action"] = next_action
    visible_trace = _filter_public_trace(session_id, artifacts["execution_trace"])
    visible_thinking = [] if _public_trace_mode(session_id) == "off" else artifacts["thinking_status"]
    skill_events = [item for item in visible_trace if item.get("skill")]
    tool_events = [item for item in visible_trace if item.get("tool")]
    return ChatResponse(
        session_id=session_id,
        assistant_message=assistant_message,
        selected_skill=selected_skill,
        route_plan=route_plan,
        evidence_gap=evidence_gap,
        knowledge_bootstrap=knowledge_bootstrap,
        progress=artifacts["progress"],
        thinking_status=visible_thinking,
        workflow_state=artifacts["workflow_state"],
        execution_trace=visible_trace,
        tool_calls=tool_calls or [],
        audit_trace=audit_trace or [],
        rag_evidence=rag_evidence,
        citations=citations or [],
        workflow_overview=overview,
        current_stage=artifacts["progress"].get("current_stage"),
        completed_stages=completed,
        pending_stages=pending,
        blocked_stages=missing,
        next_required_action=next_action,
        skill_trace=skill_events,
        tool_trace=tool_events,
        reasoning_trace=visible_thinking,
    )


def _progress_event(progress: dict) -> dict:
    return {
        "type": "progress",
        "workflow_type": progress.get("workflow_type"),
        "stage": progress.get("current_stage"),
        "progress_percent": progress.get("progress_percent"),
        "status": progress.get("status"),
        "message": progress.get("message"),
    }


def _public_trace_mode(session_id: str) -> str:
    state = get_session_state(session_id)
    return str((state.get("collected_slots") or {}).get("public_trace_mode") or "full")


def _filter_public_trace(session_id: str, events: list[dict]) -> list[dict]:
    mode = _public_trace_mode(session_id)
    if mode == "off":
        return []
    if mode == "summary":
        important = {"decision", "warning", "error", "workflow_end", "workflow_completed",
                     "workflow_failed", "tool_failed", "approval_required"}
        return [item for item in events if item.get("event_type") in important or item.get("status") in {"failed", "error"}]
    return events


def _clarification_limit_message(artifacts: dict) -> str | None:
    workflow_state = artifacts.get("workflow_state") or {}
    progress = artifacts.get("progress") or {}
    missing_slots = workflow_state.get("missing_slots") or []
    if not missing_slots:
        return None
    if workflow_state.get("clarification_round", 0) < 3:
        return None
    if progress.get("current_stage") != "clarification_round_3":
        return None
    missing = "、".join(missing_slots)
    return (
        "当前任务解析已完成 3 轮澄清，仍缺少以下关键字段："
        f"{missing}。\n\n"
        "系统可以继续生成保守任务方案，但不能进入确定性 BO 参数推荐。"
        "若要进入 BO 或给出具体参数范围，需要先补齐设备边界、目标函数和可追溯证据。"
    )


def _thinking_event(item: dict) -> dict:
    return TUIRenderer().render(item)


def _agent_trace_event(item: dict) -> dict:
    return DebugTraceRenderer().render(item)


def _handle_bootstrap_permission_reply(message: str, session_id: str, state: dict) -> dict | None:
    if not state.get("pending_bootstrap_permission"):
        return None
    text = message.strip().lower()
    active = state.get("active_knowledge_bootstrap") or {}
    if any(marker in text for marker in ["不需要", "不要", "取消", "no"]):
        active["status"] = "cancelled"
        update_session_state(session_id, {"active_knowledge_bootstrap": active, "pending_bootstrap_permission": False})
        return {
            "assistant_message": "已取消本轮外部知识冷启动。未创建候选知识，也未更新 RAG。",
            "knowledge_bootstrap": {"executed": False, "status": "cancelled"},
            "audit_trace": [{"step": "knowledge_bootstrap_permission", "status": "cancelled"}],
            "workflow_stage": "blocked_need_user_input",
            "workflow_status": "waiting_user",
        }
    if any(marker in text for marker in ["可以", "同意", "允许", "开始检索", "执行冷启动", "联网检索", "yes", "ok"]):
        return _execute_bootstrap(
            session_id,
            active.get("task_spec") or {},
            active.get("question") or message,
            None,
            state.get("evidence_gap") or {},
            [{"step": "knowledge_bootstrap_permission", "status": "granted"}],
        )
    return None


def _handle_bootstrap_chat_command(message: str, session_id: str, state: dict) -> dict | None:
    text = message.strip()
    if text == "/bootstrap status":
        return _bootstrap_status(session_id, state)
    if text == "/bootstrap off":
        active = state.get("active_knowledge_bootstrap") or {}
        active["status"] = "cancelled"
        update_session_state(session_id, {"active_knowledge_bootstrap": active, "pending_bootstrap_permission": False})
        return {
            "assistant_message": "已关闭当前会话的知识冷启动待授权状态。",
            "knowledge_bootstrap": {"executed": False, "status": "cancelled"},
            "audit_trace": [{"step": "knowledge_bootstrap", "status": "cancelled"}],
            "workflow_stage": "blocked_need_user_input",
            "workflow_status": "waiting_user",
        }
    if text == "/bootstrap on":
        update_session_state(session_id, {"pending_bootstrap_permission": True})
        return {
            "assistant_message": "已开启当前会话的知识冷启动授权等待状态。输入 /bootstrap run 可立即执行。",
            "knowledge_bootstrap": {"executed": False, "status": "awaiting_user_permission"},
            "audit_trace": [{"step": "knowledge_bootstrap", "status": "awaiting_user_permission"}],
            "workflow_stage": "knowledge_bootstrap_pending",
            "workflow_status": "waiting_user",
        }
    if text == "/bootstrap run":
        active = state.get("active_knowledge_bootstrap") or {}
        task_spec = active.get("task_spec") or _task_spec_from_message(message, None)
        question = active.get("question") or message
        return _execute_bootstrap(
            session_id,
            task_spec,
            question,
            {"primary_skill": "knowledge_bootstrap", "requires_expert_review": True},
            state.get("evidence_gap") or {},
            [{"step": "route_plan", "status": "success", "primary_skill": "knowledge_bootstrap"}],
        )
    return None


def _execute_bootstrap(
    session_id: str,
    task_spec: dict,
    question: str,
    route_plan: dict | None,
    evidence_gap: dict | None,
    audit_trace: list[dict],
) -> dict:
    cfg = load_config().get("knowledge_bootstrap", {})
    max_sources = int(cfg.get("max_sources_per_chat", 5))
    result = bootstrap_external_knowledge(task_spec=task_spec, question=question, max_sources=max_sources)
    active = {
        "task_spec": task_spec,
        "question": question,
        "candidate_ids": result["candidate_ids"],
        "review_task_ids": result["review_task_ids"],
        "status": "pending_expert_review",
    }
    update_session_state(
        session_id,
        {
            "active_knowledge_bootstrap": active,
            "pending_review_task_ids": result["review_task_ids"],
            "pending_bootstrap_permission": False,
        },
    )
    audit_trace.extend(
        [
            {
                "step": "knowledge_bootstrap",
                "status": "success",
                "created_candidates": result["created_candidates"],
            },
            {"step": "expert_review_gate", "status": "pending_review"},
        ]
    )
    return {
        "assistant_message": (
            f"已完成外部知识冷启动检索，生成 {result['created_candidates']} 条候选知识和 "
            f"{result['created_review_tasks']} 个专家审核任务。审核通过后才会进入正式 RAG；"
            "未审核候选不会用于 BO 参数推荐。"
        ),
        "selected_skill": "evidence_research",
        "route_plan": route_plan,
        "evidence_gap": evidence_gap,
        "knowledge_bootstrap": {
            "executed": True,
            "created_candidates": result["created_candidates"],
            "created_review_tasks": result["created_review_tasks"],
            "candidate_ids": result["candidate_ids"],
            "review_task_ids": result["review_task_ids"],
            "next_action": "expert_review_required",
        },
        "audit_trace": audit_trace,
        "workflow_stage": "blocked_need_expert_review",
        "workflow_status": "waiting_review",
    }


def _bootstrap_status(session_id: str, state: dict) -> dict:
    pending_ids = state.get("pending_review_task_ids") or []
    active = state.get("active_knowledge_bootstrap") or {}
    tasks = []
    for review_id in active.get("review_task_ids") or pending_ids:
        try:
            tasks.append(get_review_task(review_id))
        except ValueError:
            continue
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["review_status"]] = counts.get(task["review_status"], 0) + 1
    message = (
        f"当前会话共有 {len(active.get('candidate_ids') or [])} 条候选知识：\n"
        f"- {counts.get('accepted_to_rag', 0) + counts.get('accepted_as_literature_evidence', 0)} 条已接收入 RAG；\n"
        f"- {counts.get('needs_more_evidence', 0)} 条需要更多证据；\n"
        f"- {counts.get('pending_review', 0)} 条仍待专家审核。"
    )
    return {
        "assistant_message": message,
        "knowledge_bootstrap": {
            "active_knowledge_bootstrap": active,
            "pending_review_tasks": pending_ids,
            "counts": counts,
        },
        "audit_trace": [{"step": "knowledge_bootstrap_status", "status": "success"}],
        "workflow_stage": "blocked_need_expert_review" if counts.get("pending_review", 0) else "ready_for_rag",
        "workflow_status": "waiting_review" if counts.get("pending_review", 0) else "running",
    }


def _handle_review_guard(message: str, session_id: str, state: dict) -> dict | None:
    if "继续生成方案" not in message:
        return None
    active = state.get("active_knowledge_bootstrap") or {}
    if not active:
        return None
    if active.get("status") != "reviewed":
        return {
            "assistant_message": "仍有候选知识待审核。当前只能基于已审核知识生成初步方案，不能使用未审核候选。",
            "knowledge_bootstrap": {"active_knowledge_bootstrap": active},
            "audit_trace": [{"step": "expert_review_gate", "status": active.get("status") or "pending_review"}],
            "workflow_stage": "blocked_need_expert_review",
            "workflow_status": "waiting_review",
        }
    return None


def _task_spec_from_message(message: str, route_plan) -> dict:
    text = message.lower()
    task_spec = {}
    if "diamond" in text or "金刚石" in text:
        task_spec["material"] = "diamond"
    if "crl" in text or "透镜" in text or "x-ray" in text:
        task_spec["component_type"] = "CRL"
    if "飞秒" in text or "femtosecond" in text or "超快" in text:
        task_spec["process_type"] = "femtosecond_laser_micromachining"
    if "tgv" in text or "玻璃通孔" in text:
        task_spec.update({"scenario_id": "scenario_05_tgv_drilling", "material": "glass_wafer", "component_type": "TGV_array", "process_type": "TGV_drilling"})
    if "t300" in text:
        task_spec.update({"scenario_id": "scenario_02_surface_microstructure_bonding", "material": "CFRP_T300", "material_grade": "T300", "process_type": "surface_microtexturing"})
    elif "cfrp" in text or "碳纤维" in text:
        task_spec.update({"scenario_id": "scenario_02_surface_microstructure_bonding", "material": "CFRP"})
    if route_plan and getattr(route_plan, "primary_skill", None):
        task_spec["route_skill"] = route_plan.primary_skill
    return task_spec
