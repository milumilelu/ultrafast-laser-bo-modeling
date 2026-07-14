from __future__ import annotations

import json
import re
from typing import Any

from ultrafast_memory.agent_runtime.trace_collector import (
    list_agent_trace_events,
    record_agent_trace_event,
    trace_from_progress,
)
from ultrafast_memory.chat.workflow_projection import WorkflowProjectionService
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.bounds import build_machine_bounds


FORBIDDEN_STATUS_KEYS = {
    "chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens",
}


class LegacyWorkflowProjectionAdapter:
    """Compatibility orchestrator for old non-process chat responses."""

    @classmethod
    def build_and_persist(
        cls,
        *,
        session_id: str,
        message_id: str | None,
        task_spec: dict[str, Any],
        route_plan: Any | None = None,
        stage: str | None = None,
        status: str | None = None,
        extra_message: str | None = None,
    ) -> dict[str, Any]:
        workflow_type = getattr(route_plan, "primary_skill", None) or "task_intake"
        equipment = build_machine_bounds()
        round_no = cls._clarification_round(session_id, stage)
        projection = WorkflowProjectionService.build_legacy(
            workflow_type=workflow_type,
            task_spec=task_spec,
            equipment_snapshot=equipment,
            clarification_round=round_no,
            requires_evidence_gap=bool(getattr(route_plan, "requires_evidence_gap_check", False)),
        )
        if stage:
            projection.substatus = stage
        progress = upsert_workflow_progress(
            session_id=session_id,
            workflow_type=workflow_type,
            current_stage=projection.substatus,
            status=status or ("waiting_user" if projection.missing_fields else "running"),
            message=extra_message or projection.public_summary,
            completed_steps=projection.completed_steps,
            pending_steps=projection.pending_steps,
            missing_slots=projection.missing_fields,
        )
        thinking = cls._record_projection_events(
            session_id, message_id, progress["workflow_id"], projection.model_dump(),
            task_spec, equipment,
        )
        record_agent_trace_event(
            session_id=session_id,
            message_id=message_id,
            event_type="workflow_start",
            stage=projection.substatus,
            title="工作流启动",
            summary=f"进入 {workflow_type} 工作流。",
            progress=progress["progress_percent"],
            skill=workflow_type,
            status="running",
        )
        trace_from_progress(session_id, message_id, progress, workflow_type)
        if projection.missing_fields:
            record_agent_trace_event(
                session_id=session_id,
                message_id=message_id,
                event_type="question_generated",
                stage=projection.substatus,
                title="生成追问",
                summary="需要用户补充：" + "、".join(projection.missing_fields),
                progress=progress["progress_percent"],
                skill=workflow_type,
                status="waiting_user",
            )
        return {
            "progress": progress,
            "thinking_status": thinking,
            "workflow_state": {
                "task_spec": dict(task_spec),
                "business_state": projection.business_state,
                "substatus": projection.substatus,
                "missing_slots": projection.missing_fields,
                "clarification_round": round_no,
                "max_clarification_rounds": 3,
                "workflow_type": workflow_type,
                "current_stage": projection.substatus,
                "equipment_profile_used": cls._equipment_profile_used(equipment),
                "machine_bounds": equipment.get("machine_bounds") or {},
                "missing_equipment_fields": equipment.get("missing_equipment_fields") or [],
            },
            "execution_trace": list_agent_trace_events(session_id, message_id),
        }

    @staticmethod
    def _record_projection_events(
        session_id: str,
        message_id: str | None,
        workflow_id: str,
        projection: dict[str, Any],
        task_spec: dict[str, Any],
        equipment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events = [
            record_public_trace(
                session_id, "task_parsed", "任务事实源",
                "已从会话正式 TaskSpec 读取任务字段。", message_id, workflow_id,
                {"task_spec": task_spec},
            ),
            record_public_trace(
                session_id, "slot_check", "缺失字段投影",
                projection["public_summary"], message_id, workflow_id,
                {"missing_slots": projection["missing_fields"]},
            ),
        ]
        if projection["substatus"] == "evidence_gap_checking":
            events.append(record_public_trace(
                session_id, "evidence_gap_check", "证据检查",
                "正在检查内部知识库证据是否足够。", message_id, workflow_id,
            ))
        if equipment.get("active"):
            events.append(record_public_trace(
                session_id, "equipment_profile_loaded", "读取设备配置",
                f"已读取当前激光设备配置 {equipment.get('profile_name') or equipment.get('equipment_profile_id')}。",
                message_id, workflow_id,
                {"equipment_profile_id": equipment.get("equipment_profile_id"),
                 "revision_id": equipment.get("revision_id")},
            ))
        return events

    @staticmethod
    def _clarification_round(session_id: str, stage: str | None) -> int:
        if stage and stage.startswith("clarification_round_"):
            return min(int(stage.rsplit("_", 1)[1]), 3)
        current = get_latest_progress(session_id)
        previous = 0
        if current:
            match = re.search(r"clarification_round_(\d+)", current.get("current_stage") or "")
            if match:
                previous = int(match.group(1))
        return min(previous + 1 if previous else 1, 3)

    @staticmethod
    def _equipment_profile_used(equipment: dict[str, Any]) -> dict[str, Any] | None:
        if not equipment.get("active"):
            return None
        return {
            "equipment_profile_id": equipment.get("equipment_profile_id"),
            "profile_name": equipment.get("profile_name"),
            "revision_id": equipment.get("revision_id"),
        }


def upsert_workflow_progress(
    session_id: str,
    workflow_type: str,
    current_stage: str,
    status: str,
    message: str,
    completed_steps: list[str] | None = None,
    pending_steps: list[str] | None = None,
    missing_slots: list[str] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    workflow_id = stable_id("workflow", session_id, workflow_type)
    completed, pending = completed_steps or [], pending_steps or []
    total = len(completed) + len(pending)
    percent = round(len(completed) / total * 100, 2) if total else 100.0
    record = {
        "progress_id": stable_id("progress", session_id, workflow_type),
        "session_id": session_id, "workflow_id": workflow_id, "workflow_type": workflow_type,
        "current_stage": current_stage, "progress_percent": percent,
        "completed_steps_count": len(completed), "total_steps": total, "percent": percent,
        "status": status, "message": message, "completed_steps": completed,
        "pending_steps": pending, "missing_slots": missing_slots or [], "updated_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO workflow_progress VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record["progress_id"], session_id, workflow_id, workflow_type, current_stage,
                percent, status, message, json.dumps(completed, ensure_ascii=False),
                json.dumps(pending, ensure_ascii=False),
                json.dumps(record["missing_slots"], ensure_ascii=False), now,
            ),
        )
        conn.commit()
    return record


def record_public_trace(
    session_id: str,
    event_type: str,
    title: str,
    summary: str,
    message_id: str | None = None,
    workflow_id: str | None = None,
    detail: dict[str, Any] | None = None,
    visibility: str = "public",
) -> dict[str, Any]:
    safe = {key: value for key, value in (detail or {}).items() if key not in FORBIDDEN_STATUS_KEYS}
    return record_agent_trace_event(
        session_id=session_id, message_id=message_id, event_type=event_type,
        stage=str(safe.get("stage") or event_type), title=title, summary=summary,
        workflow_id=workflow_id, visibility=visibility, payload=safe, status="completed",
    )


def get_latest_progress(session_id: str) -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_progress WHERE session_id=? ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    value = dict(row)
    value["completed_steps"] = json.loads(value.get("completed_steps_json") or "[]")
    value["pending_steps"] = json.loads(value.get("pending_steps_json") or "[]")
    value["missing_slots"] = json.loads(value.get("missing_slots_json") or "[]")
    return value


def list_public_thinking_status(session_id: str) -> list[dict[str, Any]]:
    allowed = {
        "thinking_summary", "decision", "knowledge_lookup", "device_lookup",
        "equipment_profile_loaded", "task_parsed", "slot_check", "evidence_gap_check",
        "tool_call_started", "business_state_changed",
    }
    return [
        event for event in list_agent_trace_events(session_id)
        if event.get("visibility") == "public" and event.get("event_type") in allowed
    ]


def mark_workflow_completed(session_id: str, workflow_type: str = "task_intake") -> dict[str, Any]:
    return upsert_workflow_progress(
        session_id, workflow_type, "workflow_completed", "completed", "workflow 已完成。"
    )
