from __future__ import annotations

from .schemas import NextAction, ProcessState, WorkflowProgress


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


class ProcessStateMachine:
    def __init__(self, state: ProcessState = ProcessState.CREATED):
        self.state = state

    def transition(self, target: ProcessState) -> ProcessState:
        if target not in ALLOWED.get(self.state, set()):
            raise ValueError(f"illegal process transition: {self.state} -> {target}")
        self.state = target
        return target

    def progress(self, next_action: NextAction) -> WorkflowProgress:
        current_index = LINEAR_STAGES.index(self.state) if self.state in LINEAR_STAGES else 0
        completed = LINEAR_STAGES[:current_index]
        pending = LINEAR_STAGES[current_index + 1:]
        total = len(LINEAR_STAGES)
        return WorkflowProgress(
            workflow_overview=[{"stage": s.value, "status": "completed" if s in completed else "current" if s == self.state else "pending"} for s in LINEAR_STAGES],
            current_stage=self.state.value,
            completed_stages=[s.value for s in completed],
            pending_stages=[s.value for s in pending],
            next_required_action=next_action,
            completed_steps=len(completed), total_steps=total,
            percent=round(len(completed) / total * 100),
        )
