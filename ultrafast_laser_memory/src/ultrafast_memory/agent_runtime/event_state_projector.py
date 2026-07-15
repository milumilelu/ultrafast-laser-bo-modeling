from __future__ import annotations

from typing import Any

from ultrafast_memory.agent_runtime.trace_collector import (
    list_agent_trace_events,
    record_agent_trace_event,
)
from ultrafast_memory.chat.schemas import ChatResponse
from ultrafast_memory.chat.session_state import get_session_state


PUBLIC_STATUS_EVENT_TYPES = {
    "thinking_summary",
    "decision",
    "agent_decision",
    "knowledge_lookup",
    "device_lookup",
    "document_loaded",
    "tool_call_started",
    "tool_completed",
    "tool_failed",
    "business_state_changed",
    "approval_required",
    "warning",
    "error",
}


class EventStateProjector:
    """Build public read models only from persisted state and events that occurred."""

    @classmethod
    def project_turn(
        cls,
        *,
        session_id: str,
        assistant_message: str,
        selected_skill: str | None,
        route_plan: dict[str, Any],
        route_event: dict[str, Any],
        agent_result: dict[str, Any],
        audit_trace: list[dict[str, Any]],
        trace_mode: str = "full",
    ) -> ChatResponse:
        final_action = dict(agent_result.get("final_action") or {})
        action = str(final_action.get("action") or "unknown")
        waiting_user = action == "ask_user"
        nonterminal = action in {"call_tool", "load_skill", "unload_skill"}
        status = "waiting_user" if waiting_user else "execution_error" if nonterminal else "completed"
        progress = {
            "workflow_type": "main_agent",
            "current_stage": action,
            "progress_percent": None,
            "status": status,
            "message": final_action.get("decision_summary") or "主 Agent 已完成本轮动作。",
            "completed_steps": [],
            "pending_steps": [],
        }
        visible = cls._visible([route_event, *(agent_result.get("events") or [])], trace_mode)
        reasoning = [item for item in visible if item.get("event_type") in {"decision", "agent_decision"}]
        state = get_session_state(session_id)
        collected = dict(state.get("collected_slots") or {})
        workflow_state = dict(agent_result.get("workflow_state") or {})
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
            and (call.get("result") or {}).get("status") == "success"
        ), None)
        if equipment_call:
            equipment = dict((equipment_call.get("result") or {}).get("data") or {})
            workflow_state["equipment_profile_used"] = equipment
            workflow_state["machine_bounds"] = dict(equipment.get("machine_bounds") or {})
        next_action = {
            "action_type": "provide_clarification" if waiting_user else "execution_aborted" if nonterminal else "answer_complete",
            "required_fields": list(workflow_state.get("missing_slots") or []),
            "blocking": waiting_user,
        }
        workflow_state["next_required_action"] = next_action
        overview = [{
            "step": item.get("title") or item.get("event_type") or "agent_event",
            "status": item.get("status") or "completed",
        } for item in visible]
        return ChatResponse(
            session_id=session_id,
            assistant_message=assistant_message,
            selected_skill=selected_skill,
            route_plan=route_plan,
            progress=progress,
            thinking_status=reasoning,
            workflow_state=workflow_state,
            execution_trace=visible,
            tool_calls=agent_result.get("tool_calls") or [],
            audit_trace=audit_trace,
            workflow_overview=overview,
            current_stage=action,
            current_stage_code=action,
            next_required_action=next_action,
            skill_trace=[item for item in visible if item.get("skill")],
            tool_trace=[item for item in visible if item.get("tool")],
            reasoning_trace=reasoning,
        )

    @classmethod
    def project_command(
        cls,
        *,
        session_id: str,
        assistant_message: str,
        message_id: str | None,
        stage: str,
        status: str,
        selected_skill: str | None = None,
        route_plan: dict[str, Any] | None = None,
        evidence_gap: dict[str, Any] | None = None,
        knowledge_bootstrap: dict[str, Any] | None = None,
        audit_trace: list[dict[str, Any]] | None = None,
        trace_mode: str = "full",
    ) -> ChatResponse:
        event = record_agent_trace_event(
            session_id=session_id,
            message_id=message_id,
            event_type="decision",
            stage=stage,
            title="命令处理结果",
            summary=assistant_message,
            skill=selected_skill,
            status=status,
        )
        state = get_session_state(session_id)
        collected = dict(state.get("collected_slots") or {})
        workflow = dict(collected.get("process_workflow") or {})
        visible = cls._visible([event], trace_mode)
        waiting = status in {"waiting_user", "waiting_review"}
        next_action = {
            "action_type": "provide_input" if waiting else "command_complete",
            "required_fields": [],
            "blocking": waiting,
        }
        return ChatResponse(
            session_id=session_id,
            assistant_message=assistant_message,
            selected_skill=selected_skill,
            route_plan=route_plan,
            evidence_gap=evidence_gap,
            knowledge_bootstrap=knowledge_bootstrap,
            progress={
                "workflow_type": "main_agent",
                "current_stage": stage,
                "progress_percent": None,
                "status": status,
                "message": assistant_message,
                "completed_steps": [],
                "pending_steps": [],
            },
            thinking_status=visible,
            workflow_state={
                **workflow,
                "runtime_mode": "capability_discovery",
                "current_stage_code": stage,
                "task_spec": dict(collected.get("process_task_spec") or collected.get("task_spec") or {}),
                "next_required_action": next_action,
            },
            execution_trace=visible,
            audit_trace=audit_trace or [],
            current_stage=stage,
            current_stage_code=stage,
            next_required_action=next_action,
            skill_trace=[event] if selected_skill else [],
            reasoning_trace=visible,
        )

    @staticmethod
    def session_progress(session_id: str) -> dict[str, Any] | None:
        state = get_session_state(session_id)
        collected = dict(state.get("collected_slots") or {})
        workflow = dict(collected.get("process_workflow") or {})
        action = dict(state.get("last_agent_action_json") or workflow.get("last_agent_action") or {})
        if not action:
            return None
        action_name = str(action.get("action") or "unknown")
        return {
            "session_id": session_id,
            "workflow_type": "main_agent",
            "current_stage": action_name,
            "business_state": workflow.get("business_state") or "INTAKE",
            "progress_percent": None,
            "completed_steps": [],
            "pending_steps": [],
            "missing_slots": workflow.get("missing_slots") or [],
            "status": "waiting_user" if action_name == "ask_user" else "completed",
            "message": action.get("decision_summary") or "",
        }

    @staticmethod
    def public_status_events(session_id: str) -> list[dict[str, Any]]:
        return [
            event for event in list_agent_trace_events(session_id)
            if event.get("visibility") == "public"
            and event.get("event_type") in PUBLIC_STATUS_EVENT_TYPES
        ]

    @staticmethod
    def _visible(events: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
        if mode == "off":
            return []
        if mode == "summary":
            important = {"decision", "warning", "error", "tool_failed", "approval_required"}
            return [item for item in events if item.get("event_type") in important or item.get("status") in {"failed", "error"}]
        return events
