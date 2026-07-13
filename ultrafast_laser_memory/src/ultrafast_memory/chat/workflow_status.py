from __future__ import annotations

import json
import re
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.agent_runtime.trace_collector import (
    list_agent_trace_events,
    record_agent_trace_event,
    trace_from_progress,
    trace_from_public_status,
)


STAGE_PROGRESS = {  # legacy non-machining workflows only
    "intake_started": 5,
    "basic_info_extracted": 15,
    "missing_slots_identified": 25,
    "clarification_round_1": 40,
    "clarification_round_2": 55,
    "clarification_round_3": 70,
    "task_spec_confirmed": 80,
    "evidence_gap_checking": 85,
    "knowledge_bootstrap_pending": 88,
    "ready_for_planning": 90,
    "ready_for_rag": 92,
    "ready_for_bo": 95,
    "blocked_need_user_input": 40,
    "blocked_need_expert_review": 90,
    "workflow_completed": 100,
}

FORBIDDEN_STATUS_KEYS = {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "model_reasoning_tokens"}


def inspect_required_fields(message: str, workflow_type: str) -> list[str]:
    """Pure preflight used to enforce intake before retrieval or recommendation."""
    return _missing_slots(_parse_task(message), workflow_type, build_machine_bounds())


def parse_process_task_fields(message: str) -> dict[str, Any]:
    """Extract only explicit machining facts; never infer process parameters."""
    task = _parse_task(message)
    text = message.lower()
    length = re.search(r"(\d+(?:\.\d+)?)\s*(cm|mm)\s*(?:直线|长|长度)?", text)
    if length and not re.search(r"厚\s*" + re.escape(length.group(0)), text):
        value = float(length.group(1)) * (10 if length.group(2) == "cm" else 1)
        if value != task.get("thickness_mm"):
            task["cut_length_mm"] = value
    if "无效率要求" in text or "无硬性限制" in text or ("；无；" in message and "压缩空气" in text):
        task["efficiency_requirement"] = "none"
    if "可多次分层" in text or "允许层切" in text or "分层加工" in text:
        task["layer_cut_allowed"] = True
    if "无分层" in text:
        task["quality_requirement"] = "no_delamination"
    if "压缩空气" in text:
        task["auxiliary"] = "compressed_air"
    if "自动焦点跟踪" in text or "自动z轴" in text:
        task["focus_tracking"] = True
    return task


PROCESS_REQUIRED_FIELDS = (
    "material", "process_type", "thickness_mm", "quality_requirement",
    "cut_length_mm", "efficiency_requirement", "auxiliary", "layer_cut_allowed",
)


def missing_process_fields(task: dict[str, Any]) -> list[str]:
    return [field for field in PROCESS_REQUIRED_FIELDS if task.get(field) is None]


def build_workflow_artifacts(
    session_id: str,
    message_id: str | None,
    message: str,
    route_plan: Any | None = None,
    stage: str | None = None,
    status: str | None = None,
    extra_message: str | None = None,
) -> dict[str, Any]:
    init_database()
    workflow_type = _workflow_type(route_plan)
    task = _parse_task(message)
    equipment_context = build_machine_bounds()
    missing_slots = _missing_slots(task, workflow_type, equipment_context)
    round_no = _clarification_round(session_id, missing_slots, stage)
    current_stage = stage or _stage_for(workflow_type, missing_slots, round_no, route_plan)
    progress = upsert_workflow_progress(
        session_id=session_id,
        workflow_type=workflow_type,
        current_stage=current_stage,
        status=status or ("waiting_user" if missing_slots else "running"),
        message=extra_message or _progress_message(current_stage, missing_slots),
        completed_steps=_completed_steps(task),
        pending_steps=_pending_steps(missing_slots),
        missing_slots=missing_slots,
    )
    thinking = record_default_public_traces(
        session_id=session_id,
        message_id=message_id,
        workflow_id=progress["workflow_id"],
        task=task,
        missing_slots=missing_slots,
        equipment_context=equipment_context,
        route_plan=route_plan,
        stage=current_stage,
    )
    record_agent_trace_event(
        session_id=session_id,
        message_id=message_id,
        event_type="workflow_start",
        stage=current_stage,
        title="工作流启动",
        summary=f"进入 {workflow_type} 工作流。",
        progress=progress["progress_percent"],
        skill=workflow_type,
        status="running",
    )
    trace_from_progress(session_id, message_id, progress, workflow_type)
    for item in thinking:
        trace_from_public_status(session_id, message_id, item, workflow_type)
    if missing_slots:
        record_agent_trace_event(
            session_id=session_id,
            message_id=message_id,
            event_type="question_generated",
            stage=current_stage,
            title="生成追问",
            summary="需要用户补充：" + "、".join(missing_slots),
            progress=progress["progress_percent"],
            skill=workflow_type,
            status="waiting_user",
        )
    workflow_state = {
        "missing_slots": missing_slots,
        "clarification_round": round_no,
        "max_clarification_rounds": 3,
        "workflow_type": workflow_type,
        "current_stage": current_stage,
        "equipment_profile_used": _equipment_profile_used(equipment_context),
        "machine_bounds": equipment_context.get("machine_bounds") or {},
        "missing_equipment_fields": equipment_context.get("missing_equipment_fields") or [],
    }
    execution_trace = list_agent_trace_events(session_id, message_id)
    return {"progress": progress, "thinking_status": thinking, "workflow_state": workflow_state, "execution_trace": execution_trace}


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
    completed = completed_steps or []
    pending = pending_steps or []
    total = len(completed) + len(pending)
    calculated_percent = round(len(completed) / total * 100, 2) if total else float(STAGE_PROGRESS.get(current_stage, 0))
    record = {
        "progress_id": stable_id("progress", session_id, workflow_type),
        "session_id": session_id,
        "workflow_id": workflow_id,
        "workflow_type": workflow_type,
        "current_stage": current_stage,
        "progress_percent": calculated_percent,
        "completed_steps_count": len(completed),
        "total_steps": total,
        "percent": calculated_percent,
        "status": status,
        "message": message,
        "completed_steps": completed,
        "pending_steps": pending,
        "missing_slots": missing_slots or [],
        "updated_at": now,
    }
    db_record = {
        **record,
        "completed_steps_json": json.dumps(record["completed_steps"], ensure_ascii=False),
        "pending_steps_json": json.dumps(record["pending_steps"], ensure_ascii=False),
        "missing_slots_json": json.dumps(record["missing_slots"], ensure_ascii=False),
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_progress VALUES (
              :progress_id, :session_id, :workflow_id, :workflow_type, :current_stage,
              :progress_percent, :status, :message, :completed_steps_json,
              :pending_steps_json, :missing_slots_json, :updated_at
            )
            """,
            db_record,
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
    init_database()
    safe_detail = {k: v for k, v in (detail or {}).items() if k not in FORBIDDEN_STATUS_KEYS}
    now = utc_now_iso()
    record = {
        "trace_id": stable_id("rst", session_id, message_id or "", event_type, title, summary, now),
        "session_id": session_id,
        "message_id": message_id,
        "workflow_id": workflow_id,
        "event_type": event_type,
        "title": title,
        "summary": summary,
        "detail_json": json.dumps(safe_detail, ensure_ascii=False),
        "visibility": visibility,
        "created_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reasoning_status_trace VALUES (
              :trace_id, :session_id, :message_id, :workflow_id, :event_type,
              :title, :summary, :detail_json, :visibility, :created_at
            )
            """,
            record,
        )
        run_id = workflow_id or stable_id("workflow", session_id, "public-trace")
        sequence = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM public_reasoning_trace WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        public_payload = {
            "trace_id": record["trace_id"], "sequence": sequence, "stage": event_type,
            "event_type": event_type, "title": title, "summary": summary,
            "assumptions": [], "evidence_refs": safe_detail.get("evidence_refs") or [],
            "alternatives_considered": safe_detail.get("alternatives_considered") or [],
            "selected_alternative": safe_detail.get("selected_alternative"),
            "rejection_reasons": safe_detail.get("rejection_reasons") or [],
            "uncertainty": safe_detail.get("uncertainty") or {},
            "next_step": safe_detail.get("next_step"), "visibility": "public",
            "created_at": now,
        }
        conn.execute(
            "INSERT OR REPLACE INTO public_reasoning_trace VALUES (?,?,?,?,?,?,?,?,?)",
            (record["trace_id"], run_id, sequence, event_type, event_type, title, summary,
             json.dumps(public_payload, ensure_ascii=False), now),
        )
        conn.commit()
    return {key: value for key, value in record.items() if key != "detail_json"}


def record_default_public_traces(
    session_id: str,
    message_id: str | None,
    workflow_id: str,
    task: dict[str, Any],
    missing_slots: list[str],
    equipment_context: dict[str, Any],
    route_plan: Any | None,
    stage: str,
) -> list[dict[str, Any]]:
    summaries = [
        (
            "task_parsed",
            "任务解析",
            _task_summary(task),
            {"task_spec": task},
        ),
        (
            "slot_check",
            "缺失字段检查",
            _slot_summary(missing_slots),
            {"missing_slots": missing_slots},
        ),
    ]
    if stage == "evidence_gap_checking":
        summaries.append(("evidence_gap_check", "证据检查", "正在检查内部知识库证据是否足够。", {}))
    if equipment_context.get("active"):
        profile = equipment_context.get("profile_name") or equipment_context.get("equipment_profile_id")
        bounds = equipment_context.get("machine_bounds") or {}
        loaded = [key for key in ("laser_power_W", "frequency_kHz", "scan_speed_mm_s") if key in bounds]
        summaries.append(
            (
                "equipment_profile_loaded",
                "读取设备配置",
                f"已读取当前激光设备配置 {profile}，并自动填充" + "、".join(loaded) + "边界。",
                {
                    "equipment_profile_id": equipment_context.get("equipment_profile_id"),
                    "revision_id": equipment_context.get("revision_id"),
                    "machine_bounds": bounds,
                },
            )
        )
    events = []
    for event_type, title, summary, detail in summaries:
        events.append(record_public_trace(session_id, event_type, title, summary, message_id, workflow_id, detail))
    return events


def get_latest_progress(session_id: str) -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_progress WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    return _progress_row(dict(row)) if row else None


def list_public_thinking_status(session_id: str) -> list[dict[str, Any]]:
    init_database()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT trace_id, session_id, message_id, workflow_id, event_type, title, summary, visibility, created_at
            FROM reasoning_status_trace
            WHERE session_id = ? AND visibility = 'public'
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_workflow_completed(session_id: str, workflow_type: str = "task_intake") -> dict[str, Any]:
    return upsert_workflow_progress(
        session_id=session_id,
        workflow_type=workflow_type,
        current_stage="workflow_completed",
        status="completed",
        message="workflow 已完成。",
    )


def _progress_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "completed_steps": _loads(row.get("completed_steps_json"), []),
        "pending_steps": _loads(row.get("pending_steps_json"), []),
        "missing_slots": _loads(row.get("missing_slots_json"), []),
    }


def _workflow_type(route_plan: Any | None) -> str:
    primary = getattr(route_plan, "primary_skill", None) if route_plan is not None else None
    return primary or "task_intake"


def _stage_for(workflow_type: str, missing_slots: list[str], round_no: int, route_plan: Any | None) -> str:
    if missing_slots:
        return f"clarification_round_{min(max(round_no, 1), 3)}"
    if getattr(route_plan, "requires_evidence_gap_check", False):
        return "evidence_gap_checking"
    if workflow_type == "rag_literature_retrieval":
        return "ready_for_rag"
    if workflow_type == "bo_recommendation":
        return "ready_for_bo"
    return "task_spec_confirmed"


def _parse_task(message: str) -> dict[str, Any]:
    text = message.lower()
    task: dict[str, Any] = {}
    if "diamond" in text or "金刚石" in text:
        task["material"] = "diamond"
    if "cfrp" in text or "碳纤维" in text or "t300" in text:
        task["material"] = "CFRP_T300" if "t300" in text else "CFRP"
    thickness = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*(?:厚)?", text)
    if thickness:
        task["thickness_mm"] = float(thickness.group(1))
    if "切割" in text or "cutting" in text:
        task["process_type"] = "cutting"
        task["component_type"] = "workpiece"
    if "无分层" in text or "delamination" in text:
        task["quality_requirement"] = "no_delamination"
    if "压缩空气" in text or "compressed air" in text:
        task["auxiliary"] = "compressed_air"
    if "允许层切" in text:
        task["layer_cut_allowed"] = True
    if "crl" in text or "透镜" in text or "x-ray" in text:
        task["component_type"] = "CRL"
    if "飞秒" in text or "femtosecond" in text or "超快" in text:
        task["process_type"] = "femtosecond_laser_micromachining"
    roughness = re.search(r"ra\s*[<小于]*\s*(\d+(\.\d+)?)\s*(nm|um|µm)?", message, re.IGNORECASE)
    if roughness:
        task["roughness_target"] = f"Ra < {roughness.group(1)} {roughness.group(3) or 'nm'}"
    if "单晶" in message or "single crystal" in text:
        task["diamond_type"] = "single_crystal"
    if any(marker in text for marker in ["1030", "515", "800", "fs", "khz", "w"]):
        task["laser_system"] = "mentioned"
    if "后处理" in message:
        task["post_processing_allowed"] = "mentioned"
    return task


def _missing_slots(task: dict[str, Any], workflow_type: str, equipment_context: dict[str, Any]) -> list[str]:
    if workflow_type not in {"task_intake", "crl_task_planning", "rag_literature_retrieval", "bo_recommendation", "complex_process_task"}:
        return []
    missing = []
    if workflow_type == "complex_process_task":
        for slot in ("material", "process_type", "thickness_mm", "quality_requirement"):
            if not task.get(slot):
                missing.append(slot)
    if task.get("component_type") == "CRL" or task.get("material") == "diamond":
        for slot in ("diamond_type", "post_processing_allowed"):
            if not task.get(slot):
                missing.append(slot)
        if equipment_context.get("active"):
            missing.extend(equipment_context.get("missing_equipment_fields") or [])
        elif not task.get("laser_system"):
            missing.append("laser_system")
    if workflow_type == "bo_recommendation":
        for slot in ("objective", "training_sample_count"):
            if not task.get(slot):
                missing.append(slot)
    return missing


def _clarification_round(session_id: str, missing_slots: list[str], stage: str | None) -> int:
    current = get_latest_progress(session_id)
    previous = 0
    if current:
        match = re.search(r"clarification_round_(\d+)", current.get("current_stage") or "")
        if match:
            previous = int(match.group(1))
    if stage and stage.startswith("clarification_round_"):
        return min(int(stage.rsplit("_", 1)[1]), 3)
    if missing_slots:
        return min(previous + 1 if previous else 1, 3)
    return previous


def _completed_steps(task: dict[str, Any]) -> list[str]:
    labels = {
        "material": "识别材料",
        "component_type": "识别对象",
        "process_type": "识别工艺",
        "roughness_target": "识别质量目标",
    }
    return [f"{label}：{task[key]}" for key, label in labels.items() if task.get(key)]


def _pending_steps(missing_slots: list[str]) -> list[str]:
    labels = {
        "diamond_type": "确认金刚石类型",
        "laser_system": "确认激光器参数范围",
        "post_processing_allowed": "确认是否允许后处理",
        "objective": "确认目标函数",
        "training_sample_count": "确认有效训练样本数量",
        "pulse_width_fs": "确认脉宽范围",
        "laser_power_W": "确认激光功率范围",
        "frequency_kHz": "确认重复频率范围",
        "scan_speed_mm_s": "确认扫描速度范围",
        "spot_diameter_um": "确认光斑直径",
    }
    return [labels.get(slot, slot) for slot in missing_slots]


def _progress_message(stage: str, missing_slots: list[str]) -> str:
    if stage == "evidence_gap_checking":
        return "正在检查内部知识库证据是否足够。"
    if stage == "knowledge_bootstrap_pending":
        return "内部证据不足，等待用户授权外部知识冷启动。"
    if missing_slots:
        return "已完成基本任务识别，正在补齐关键约束。"
    return "任务关键信息已基本确认。"


def _task_summary(task: dict[str, Any]) -> str:
    if not task:
        return "尚未识别到足够任务字段。"
    parts = []
    if task.get("material"):
        parts.append(f"材料 {task['material']}")
    if task.get("component_type"):
        parts.append(f"对象 {task['component_type']}")
    if task.get("roughness_target"):
        parts.append(f"目标 {task['roughness_target']}")
    return "已识别" + "、".join(parts) + "。" if parts else "已提取部分任务描述。"


def _slot_summary(missing_slots: list[str]) -> str:
    if not missing_slots:
        return "关键字段已基本满足当前阶段要求。"
    return "仍缺少：" + "、".join(missing_slots) + "。"


def _equipment_profile_used(equipment_context: dict[str, Any]) -> dict[str, Any] | None:
    if not equipment_context.get("active"):
        return None
    return {
        "equipment_profile_id": equipment_context.get("equipment_profile_id"),
        "profile_name": equipment_context.get("profile_name"),
        "revision_id": equipment_context.get("revision_id"),
    }


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
