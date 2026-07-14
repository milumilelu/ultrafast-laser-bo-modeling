from __future__ import annotations

from .schemas import NextAction, ProcessState, WorkflowProgress
from .business_state import BUSINESS_STATE_ORDER, BusinessState, business_state_for


LINEAR_STAGES = [
    ProcessState.INTAKE, ProcessState.REQUIREMENTS_CONFIRMED,
    ProcessState.EQUIPMENT_LOADING, ProcessState.EVIDENCE_RETRIEVAL,
    ProcessState.EVIDENCE_ASSESSMENT, ProcessState.TRIAL_ASSESSMENT,
    ProcessState.TRIAL_MODE_PENDING, ProcessState.TRIAL_PLAN_READY,
    ProcessState.TRIAL_EXECUTION_PENDING, ProcessState.TRIAL_RESULT_PENDING,
    ProcessState.TRIAL_RESULT_EVALUATION, ProcessState.KNOWLEDGE_APPROVAL_PENDING,
    ProcessState.BO_READY, ProcessState.BO_RUNNING, ProcessState.FORMAL_PROCESS_READY,
    ProcessState.FORMAL_RELEASE_PENDING, ProcessState.FORMAL_PREFLIGHT,
    ProcessState.FORMAL_PROCESS_RUNNING, ProcessState.FINAL_INSPECTION_PENDING,
    ProcessState.QUALITY_DECISION, ProcessState.REPORT_PENDING,
    ProcessState.ARCHIVE_PENDING, ProcessState.COMPLETED,
]

ALLOWED = {ProcessState.CREATED: {ProcessState.INTAKE}}
for left, right in zip(LINEAR_STAGES, LINEAR_STAGES[1:]):
    ALLOWED.setdefault(left, set()).add(right)
ALLOWED[ProcessState.INTAKE].add(ProcessState.REQUIREMENTS_PENDING)
ALLOWED[ProcessState.REQUIREMENTS_PENDING] = {ProcessState.REQUIREMENTS_CONFIRMED, ProcessState.BLOCKED}
ALLOWED[ProcessState.TRIAL_ASSESSMENT].add(ProcessState.BLOCKED)
ALLOWED[ProcessState.TRIAL_RESULT_EVALUATION].update({ProcessState.BO_READY, ProcessState.BLOCKED})
ALLOWED[ProcessState.QUALITY_DECISION].update({ProcessState.REWORK_PENDING, ProcessState.BLOCKED})
ALLOWED[ProcessState.REWORK_PENDING] = {ProcessState.TRIAL_ASSESSMENT, ProcessState.BLOCKED}


class LegacyProcessStateAdapter:
    """Read-compatible fine-state adapter; BusinessState is authoritative."""

    def __init__(self, state: ProcessState = ProcessState.CREATED):
        self.state = state

    def transition(self, target: ProcessState) -> ProcessState:
        if target not in ALLOWED.get(self.state, set()):
            raise ValueError(f"illegal process transition: {self.state} -> {target}")
        self.state = target
        return target

    @property
    def business_state(self) -> BusinessState:
        return business_state_for(self.state.value)

    def progress(self, next_action: NextAction) -> WorkflowProgress:
        business_state = self.business_state
        current_index = (
            BUSINESS_STATE_ORDER.index(business_state)
            if business_state in BUSINESS_STATE_ORDER else 0
        )
        completed = BUSINESS_STATE_ORDER[:current_index]
        pending = BUSINESS_STATE_ORDER[current_index + 1:]
        total = len(BUSINESS_STATE_ORDER)
        return WorkflowProgress(
            workflow_overview=[{"stage": s.value, "status": "completed" if s in completed else "current" if s == business_state else "pending"} for s in BUSINESS_STATE_ORDER],
            current_stage=business_state.value,
            completed_stages=[s.value for s in completed],
            pending_stages=[s.value for s in pending],
            next_required_action=next_action,
            completed_steps=len(completed), total_steps=total,
            percent=round(len(completed) / total * 100),
        )


ProcessStateMachine = LegacyProcessStateAdapter
