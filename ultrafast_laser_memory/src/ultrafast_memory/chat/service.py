from __future__ import annotations

from collections.abc import Iterator

from ultrafast_agent.observability import DebugTraceRenderer, TUIRenderer
from ultrafast_memory.agent_runtime.event_state_projector import EventStateProjector
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.chat.router.debug_commands import handle_debug_command
from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.chat.schemas import ChatRequest, ChatResponse
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.chat.session_store import (
    create_session,
    save_message,
    save_skill_trace,
    session_exists,
)
from ultrafast_memory.core.config import load_config
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge
from ultrafast_memory.knowledge_review.review_queue import get_review_task
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn


def handle_chat(request: ChatRequest) -> ChatResponse:
    session_id = _ensure_session(request)

    user_message = save_message(session_id, "user", request.message, {"mode": request.mode})
    state = get_session_state(session_id)

    mode_command = _handle_display_mode_command(request.message, session_id)
    if mode_command:
        save_message(session_id, "assistant", mode_command["assistant_message"], {"display_mode": mode_command.get("display_mode")})
        return EventStateProjector.project_command(
            session_id=session_id,
            assistant_message=mode_command["assistant_message"],
            message_id=user_message["message_id"],
            stage="display_mode",
            status="completed",
            audit_trace=[{"step": "display_mode", "status": "success", "mode": mode_command.get("display_mode")}],
            trace_mode=_public_trace_mode(session_id),
        )

    bootstrap_command = _handle_bootstrap_chat_command(request.message, session_id, state)
    if bootstrap_command:
        save_message(session_id, "assistant", bootstrap_command["assistant_message"], {"knowledge_bootstrap": bootstrap_command.get("knowledge_bootstrap")})
        return EventStateProjector.project_command(
            session_id=session_id,
            assistant_message=bootstrap_command["assistant_message"],
            message_id=user_message["message_id"],
            selected_skill=bootstrap_command.get("selected_skill"),
            route_plan=bootstrap_command.get("route_plan"),
            evidence_gap=bootstrap_command.get("evidence_gap"),
            knowledge_bootstrap=bootstrap_command.get("knowledge_bootstrap"),
            audit_trace=bootstrap_command.get("audit_trace", []),
            stage=bootstrap_command.get("command_stage") or "command_complete",
            status=bootstrap_command.get("command_status") or "completed",
            trace_mode=_public_trace_mode(session_id),
        )

    permission_result = _handle_bootstrap_permission_reply(request.message, session_id, state)
    if permission_result:
        save_message(session_id, "assistant", permission_result["assistant_message"], {"knowledge_bootstrap": permission_result.get("knowledge_bootstrap")})
        return EventStateProjector.project_command(
            session_id=session_id,
            assistant_message=permission_result["assistant_message"],
            message_id=user_message["message_id"],
            selected_skill=permission_result.get("selected_skill"),
            route_plan=permission_result.get("route_plan"),
            evidence_gap=permission_result.get("evidence_gap"),
            knowledge_bootstrap=permission_result.get("knowledge_bootstrap"),
            audit_trace=permission_result.get("audit_trace", []),
            stage=permission_result.get("command_stage") or "command_complete",
            status=permission_result.get("command_status") or "completed",
            trace_mode=_public_trace_mode(session_id),
        )

    continuation_guard = _handle_review_guard(request.message, session_id, state)
    if continuation_guard:
        save_message(session_id, "assistant", continuation_guard["assistant_message"], {"knowledge_bootstrap": continuation_guard.get("knowledge_bootstrap")})
        return EventStateProjector.project_command(
            session_id=session_id,
            assistant_message=continuation_guard["assistant_message"],
            message_id=user_message["message_id"],
            selected_skill=continuation_guard.get("selected_skill"),
            route_plan=continuation_guard.get("route_plan"),
            knowledge_bootstrap=continuation_guard.get("knowledge_bootstrap"),
            audit_trace=continuation_guard.get("audit_trace", []),
            stage=continuation_guard.get("command_stage") or "command_complete",
            status=continuation_guard.get("command_status") or "completed",
            trace_mode=_public_trace_mode(session_id),
        )

    debug_command = handle_debug_command(request.message, session_id)
    if debug_command and not request.message.strip().startswith("/skill "):
        assistant_content = _debug_response(debug_command)
        save_message(session_id, "assistant", assistant_content, {"debug_command": True})
        return EventStateProjector.project_command(
            session_id=session_id,
            assistant_message=assistant_content,
            message_id=user_message["message_id"],
            stage="debug_command",
            status="completed",
            audit_trace=[{"step": "debug_command", "status": "success"}],
            trace_mode=_public_trace_mode(session_id),
        )

    route_plan = route_message(request.message, session_id, user_message["message_id"])
    selected_skill = route_plan.primary_skill
    route_event = _record_route_decision_trace(
        session_id, user_message["message_id"], request.message, route_plan
    )
    save_skill_trace(session_id, user_message["message_id"], {
        "selected_skill": selected_skill,
        "confidence": route_plan.confidence,
        "reason": route_plan.reason,
    })
    audit_trace = [{
        "step": "hybrid_router",
        "status": "success",
        "selected_skill": selected_skill,
        "route_source": route_plan.route_source,
    }]
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
    save_message(session_id, "assistant", assistant_content, {
        "selected_skill": selected_skill,
        "active_skills": agent_result["active_skills"],
        "suggested_skills": suggested_skills,
        "route_plan": route_plan.model_dump(mode="json"),
        "tool_calls": agent_result["tool_calls"],
    })
    return EventStateProjector.project_turn(
        session_id=session_id,
        assistant_message=assistant_content,
        selected_skill=selected_skill,
        route_plan=route_plan.model_dump(mode="json"),
        route_event=route_event,
        agent_result=agent_result,
        audit_trace=audit_trace,
        trace_mode=_public_trace_mode(session_id),
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
            "command_stage": "blocked_need_user_input",
            "command_status": "waiting_user",
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
            "command_stage": "blocked_need_user_input",
            "command_status": "waiting_user",
        }
    if text == "/bootstrap on":
        update_session_state(session_id, {"pending_bootstrap_permission": True})
        return {
            "assistant_message": "已开启当前会话的知识冷启动授权等待状态。输入 /bootstrap run 可立即执行。",
            "knowledge_bootstrap": {"executed": False, "status": "awaiting_user_permission"},
            "audit_trace": [{"step": "knowledge_bootstrap", "status": "awaiting_user_permission"}],
            "command_stage": "knowledge_bootstrap_pending",
            "command_status": "waiting_user",
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
        "command_stage": "blocked_need_expert_review",
        "command_status": "waiting_review",
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
        "command_stage": "blocked_need_expert_review" if counts.get("pending_review", 0) else "ready_for_rag",
        "command_status": "waiting_review" if counts.get("pending_review", 0) else "running",
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
            "command_stage": "blocked_need_expert_review",
            "command_status": "waiting_review",
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
