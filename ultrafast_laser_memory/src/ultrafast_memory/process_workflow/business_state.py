from __future__ import annotations

from enum import StrEnum
from typing import Any


class BusinessState(StrEnum):
    INTAKE = "INTAKE"
    EVIDENCE = "EVIDENCE"
    TRIAL = "TRIAL"
    REVIEW = "REVIEW"
    OPTIMIZATION = "OPTIMIZATION"
    READY_FOR_EXTERNAL_PROCESS = "READY_FOR_EXTERNAL_PROCESS"
    WAITING_EXTERNAL_RESULT = "WAITING_EXTERNAL_RESULT"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


BUSINESS_STATE_ORDER = (
    BusinessState.INTAKE,
    BusinessState.EVIDENCE,
    BusinessState.TRIAL,
    BusinessState.REVIEW,
    BusinessState.OPTIMIZATION,
    BusinessState.READY_FOR_EXTERNAL_PROCESS,
    BusinessState.WAITING_EXTERNAL_RESULT,
    BusinessState.QUALITY_REVIEW,
    BusinessState.COMPLETED,
)

BUSINESS_STATE_LABELS = {
    BusinessState.INTAKE: "需求确认",
    BusinessState.EVIDENCE: "证据准备",
    BusinessState.TRIAL: "试切",
    BusinessState.REVIEW: "审核",
    BusinessState.OPTIMIZATION: "优化",
    BusinessState.READY_FOR_EXTERNAL_PROCESS: "外部加工准备",
    BusinessState.WAITING_EXTERNAL_RESULT: "等待外部加工结果",
    BusinessState.QUALITY_REVIEW: "质量复核",
    BusinessState.COMPLETED: "已完成",
    BusinessState.BLOCKED: "已阻塞",
}

ALLOWED_BUSINESS_TRANSITIONS = {
    BusinessState.INTAKE: {BusinessState.EVIDENCE, BusinessState.TRIAL, BusinessState.BLOCKED},
    BusinessState.EVIDENCE: {BusinessState.TRIAL, BusinessState.REVIEW, BusinessState.OPTIMIZATION, BusinessState.BLOCKED},
    BusinessState.TRIAL: {BusinessState.REVIEW, BusinessState.OPTIMIZATION, BusinessState.READY_FOR_EXTERNAL_PROCESS, BusinessState.BLOCKED},
    BusinessState.REVIEW: {BusinessState.TRIAL, BusinessState.OPTIMIZATION, BusinessState.READY_FOR_EXTERNAL_PROCESS, BusinessState.BLOCKED},
    BusinessState.OPTIMIZATION: {BusinessState.TRIAL, BusinessState.REVIEW, BusinessState.READY_FOR_EXTERNAL_PROCESS, BusinessState.BLOCKED},
    BusinessState.READY_FOR_EXTERNAL_PROCESS: {BusinessState.WAITING_EXTERNAL_RESULT, BusinessState.TRIAL, BusinessState.BLOCKED},
    BusinessState.WAITING_EXTERNAL_RESULT: {BusinessState.QUALITY_REVIEW, BusinessState.TRIAL, BusinessState.BLOCKED},
    BusinessState.QUALITY_REVIEW: {BusinessState.OPTIMIZATION, BusinessState.TRIAL, BusinessState.COMPLETED, BusinessState.BLOCKED},
    BusinessState.BLOCKED: {BusinessState.INTAKE, BusinessState.TRIAL, BusinessState.REVIEW, BusinessState.OPTIMIZATION, BusinessState.READY_FOR_EXTERNAL_PROCESS},
    BusinessState.COMPLETED: set(),
}


LEGACY_STATE_MIGRATION = {
    "CREATED": BusinessState.INTAKE,
    "INTAKE": BusinessState.INTAKE,
    "REQUIREMENTS_PENDING": BusinessState.INTAKE,
    "PARSER_STALL": BusinessState.INTAKE,
    "REQUIREMENTS_CONFIRMED": BusinessState.INTAKE,
    "EQUIPMENT_LOADING": BusinessState.EVIDENCE,
    "EVIDENCE_RETRIEVAL": BusinessState.EVIDENCE,
    "EVIDENCE_ASSESSMENT": BusinessState.EVIDENCE,
    "TRIAL_ASSESSMENT": BusinessState.TRIAL,
    "TRIAL_MODE_PENDING": BusinessState.TRIAL,
    "TRIAL_PLAN_READY": BusinessState.TRIAL,
    "TRIAL_EXECUTION_PENDING": BusinessState.TRIAL,
    "TRIAL_RESULT_PENDING": BusinessState.TRIAL,
    "TRIAL_RESULT_EVALUATION": BusinessState.REVIEW,
    "KNOWLEDGE_APPROVAL_PENDING": BusinessState.REVIEW,
    "PARAMETER_SOURCE_APPROVAL_PENDING": BusinessState.REVIEW,
    "BO_READY": BusinessState.OPTIMIZATION,
    "BO_RUNNING": BusinessState.OPTIMIZATION,
    "REWORK_PENDING": BusinessState.OPTIMIZATION,
    "FORMAL_PROCESS_READY": BusinessState.READY_FOR_EXTERNAL_PROCESS,
    "FORMAL_RELEASE_PENDING": BusinessState.READY_FOR_EXTERNAL_PROCESS,
    "FORMAL_PREFLIGHT": BusinessState.READY_FOR_EXTERNAL_PROCESS,
    "FORMAL_PROCESS_RUNNING": BusinessState.WAITING_EXTERNAL_RESULT,
    "FINAL_INSPECTION_PENDING": BusinessState.QUALITY_REVIEW,
    "QUALITY_DECISION": BusinessState.QUALITY_REVIEW,
    "REPORT_PENDING": BusinessState.QUALITY_REVIEW,
    "ARCHIVE_PENDING": BusinessState.QUALITY_REVIEW,
    "COMPLETED": BusinessState.COMPLETED,
    "BLOCKED": BusinessState.BLOCKED,
    "FAILED": BusinessState.BLOCKED,
}


def business_state_for(substatus: str) -> BusinessState:
    try:
        return LEGACY_STATE_MIGRATION[substatus]
    except KeyError as exc:
        raise ValueError(f"unknown process substatus: {substatus}") from exc


class BusinessStateController:
    """Canonical business state writer with legacy state read compatibility."""

    @staticmethod
    def ensure(workflow: dict[str, Any], default_substatus: str = "INTAKE") -> dict[str, Any]:
        substatus = str(workflow.get("substatus") or workflow.get("state") or default_substatus)
        mapped = business_state_for(substatus)
        if workflow.get("business_state"):
            business_state = BusinessState(str(workflow["business_state"]))
            if business_state != mapped:
                workflow["state_projection_warning"] = "legacy_substatus_mismatch"
        else:
            business_state = mapped
        workflow["substatus"] = substatus
        workflow["state"] = substatus  # read compatibility for persisted V3 records
        workflow["business_state"] = business_state.value
        workflow["business_state_changed"] = False
        return workflow

    @staticmethod
    def transition(workflow: dict[str, Any], substatus: str) -> dict[str, Any]:
        previous = workflow.get("business_state")
        business_state = business_state_for(substatus)
        if previous:
            previous_state = BusinessState(str(previous))
            if (
                previous_state != business_state
                and business_state not in ALLOWED_BUSINESS_TRANSITIONS[previous_state]
            ):
                raise ValueError(
                    f"illegal business transition: {previous_state.value} -> {business_state.value}"
                )
        workflow["substatus"] = substatus
        workflow["state"] = substatus  # legacy read adapter; not a second state calculation
        workflow["business_state"] = business_state.value
        changed = previous != business_state.value
        workflow["business_state_changed"] = changed
        if changed:
            workflow["business_state_transition"] = {
                "from": previous,
                "to": business_state.value,
                "substatus": substatus,
            }
        return workflow
