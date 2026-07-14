from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ultrafast_agent.task_intake.missing_field_service import MissingFieldEvaluator
from ultrafast_agent.task_intake.schemas import PROCESS_REQUIRED_FIELDS
from ultrafast_memory.process_workflow.business_state import (
    BUSINESS_STATE_LABELS,
    BUSINESS_STATE_ORDER,
    BusinessState,
    BusinessStateController,
)


class WorkflowProjection(BaseModel):
    workflow_type: str
    business_state: str
    substatus: str
    progress_percent: float
    missing_fields: list[str] = Field(default_factory=list)
    current_step: str | None = None
    next_action: dict[str, Any] = Field(default_factory=dict)
    public_summary: str
    workflow_overview: list[dict[str, Any]] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)


class WorkflowProjectionService:
    """Pure read model: no parsing, state mutation, event creation, or persistence."""

    @classmethod
    def build_process(
        cls,
        *,
        task_spec: dict[str, Any],
        workflow_state: dict[str, Any],
        recent_events: list[dict[str, Any]] | None = None,
        next_action: dict[str, Any] | None = None,
    ) -> WorkflowProjection:
        canonical = BusinessStateController.ensure(dict(workflow_state))
        business_state = BusinessState(canonical["business_state"])
        missing = MissingFieldEvaluator.evaluate(task_spec)
        completed_count = cls._completed_business_states(business_state)
        overview = cls._business_overview(business_state, completed_count)
        pending = [item["step"] for item in overview if item["status_code"] == "pending"]
        completed = [item["step"] for item in overview if item["status_code"] == "completed"]
        return WorkflowProjection(
            workflow_type="complex_process_task",
            business_state=business_state.value,
            substatus=canonical["substatus"],
            progress_percent=cls._business_percent(
                business_state,
                completed_count,
                task_fields_complete=len(PROCESS_REQUIRED_FIELDS) - len(missing),
            ),
            missing_fields=missing,
            current_step=cls._current_step(recent_events),
            next_action=dict(next_action or {}),
            public_summary=(
                f"当前业务状态为 {BUSINESS_STATE_LABELS[business_state]}；"
                f"substatus={canonical['substatus']}。"
            ),
            workflow_overview=overview,
            completed_steps=completed,
            pending_steps=pending,
        )

    @classmethod
    def build_legacy(
        cls,
        *,
        workflow_type: str,
        task_spec: dict[str, Any],
        equipment_snapshot: dict[str, Any],
        clarification_round: int,
        requires_evidence_gap: bool = False,
    ) -> WorkflowProjection:
        missing = cls._legacy_missing_fields(task_spec, workflow_type, equipment_snapshot)
        if missing:
            substatus = f"clarification_round_{min(max(clarification_round, 1), 3)}"
            business_state = BusinessState.INTAKE
        elif requires_evidence_gap:
            substatus = "evidence_gap_checking"
            business_state = BusinessState.EVIDENCE
        elif workflow_type == "rag_literature_retrieval":
            substatus, business_state = "ready_for_rag", BusinessState.EVIDENCE
        elif workflow_type == "bo_recommendation":
            substatus, business_state = "ready_for_bo", BusinessState.OPTIMIZATION
        else:
            substatus, business_state = "task_spec_confirmed", BusinessState.INTAKE
        completed = cls._legacy_completed_steps(task_spec)
        pending = cls._legacy_pending_steps(missing)
        total = len(completed) + len(pending)
        percent = round(len(completed) / total * 100, 2) if total else 100.0
        return WorkflowProjection(
            workflow_type=workflow_type,
            business_state=business_state.value,
            substatus=substatus,
            progress_percent=percent,
            missing_fields=missing,
            next_action={
                "action_type": "submit_required_fields" if missing else "continue_workflow",
                "required_fields": missing,
                "blocking": bool(missing),
            },
            public_summary=(
                "已读取正式 TaskSpec，仍缺少：" + "、".join(missing) + "。"
                if missing else "已读取正式 TaskSpec，当前阶段字段已满足。"
            ),
            completed_steps=completed,
            pending_steps=pending,
        )

    @staticmethod
    def _completed_business_states(state: BusinessState) -> int:
        if state == BusinessState.COMPLETED:
            return len(BUSINESS_STATE_ORDER)
        return BUSINESS_STATE_ORDER.index(state) if state in BUSINESS_STATE_ORDER else 0

    @staticmethod
    def _business_percent(
        state: BusinessState,
        completed_count: int,
        *,
        task_fields_complete: int = 0,
    ) -> int:
        if state == BusinessState.COMPLETED:
            return 100
        if state == BusinessState.INTAKE:
            intake_fraction = task_fields_complete / len(PROCESS_REQUIRED_FIELDS)
            return round(intake_fraction / len(BUSINESS_STATE_ORDER) * 100)
        return round(completed_count / len(BUSINESS_STATE_ORDER) * 100)

    @staticmethod
    def _business_overview(state: BusinessState, completed_count: int) -> list[dict[str, Any]]:
        result = []
        for index, item in enumerate(BUSINESS_STATE_ORDER):
            status = "completed" if index < completed_count else "current" if item == state else "pending"
            result.append({
                "step_code": item.value,
                "step": BUSINESS_STATE_LABELS[item],
                "status_code": status,
            })
        return result

    @staticmethod
    def _current_step(events: list[dict[str, Any]] | None) -> str | None:
        for event in reversed(events or []):
            if event.get("step"):
                return str(event["step"])
        return None

    @staticmethod
    def _legacy_missing_fields(
        task: dict[str, Any], workflow_type: str, equipment: dict[str, Any]
    ) -> list[str]:
        if workflow_type not in {
            "task_intake", "crl_task_planning", "rag_literature_retrieval", "bo_recommendation",
        }:
            return []
        missing: list[str] = []
        if task.get("component_type") == "CRL" or task.get("material") == "diamond":
            for field in ("diamond_type", "post_processing_allowed"):
                if not task.get(field):
                    missing.append(field)
            if equipment.get("active"):
                missing.extend(equipment.get("missing_equipment_fields") or [])
            elif not task.get("laser_system"):
                missing.append("laser_system")
        if workflow_type == "bo_recommendation":
            for field in ("objective", "training_sample_count"):
                if not task.get(field):
                    missing.append(field)
        return missing

    @staticmethod
    def _legacy_completed_steps(task: dict[str, Any]) -> list[str]:
        labels = {
            "material": "识别材料", "component_type": "识别对象",
            "process_type": "识别工艺", "roughness_target": "识别质量目标",
        }
        return [f"{label}：{task[key]}" for key, label in labels.items() if task.get(key)]

    @staticmethod
    def _legacy_pending_steps(missing: list[str]) -> list[str]:
        labels = {
            "diamond_type": "确认金刚石类型", "laser_system": "确认激光器参数范围",
            "post_processing_allowed": "确认是否允许后处理", "objective": "确认目标函数",
            "training_sample_count": "确认有效训练样本数量",
        }
        return [labels.get(field, field) for field in missing]
