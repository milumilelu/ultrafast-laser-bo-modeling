from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ClarificationContext,
    EXPECTED_ANSWER_TYPES,
    PROCESS_REQUIRED_FIELDS,
)


class ClarificationContextService:
    @staticmethod
    def build(
        session_state: dict[str, Any],
        workflow_type: str,
        current_spec: dict[str, Any] | None = None,
    ) -> ClarificationContext:
        collected = session_state.get("collected_slots") or {}
        workflow = collected.get("process_workflow") or {}
        pending = list(workflow.get("missing_fields") or session_state.get("pending_questions") or [])
        if not pending:
            spec = current_spec or collected.get("process_task_spec") or {}
            pending = [field for field in PROCESS_REQUIRED_FIELDS if spec.get(field) is None]
        pending = [field for field in pending if field in EXPECTED_ANSWER_TYPES]
        stored_round = int(workflow.get("clarification_round") or 0)
        current_round = stored_round + 1 if workflow.get("state") in {"REQUIREMENTS_PENDING", "PARSER_STALL"} else stored_round
        return ClarificationContext(
            workflow_type=workflow_type,
            stage=str(workflow.get("state") or session_state.get("workflow_stage") or "INTAKE"),
            clarification_round=current_round,
            pending_fields=pending,
            ordered_fields=list(workflow.get("ordered_fields") or pending),
            previous_questions=list(workflow.get("previous_questions") or []),
            expected_answer_types={field: EXPECTED_ANSWER_TYPES[field] for field in pending},
        )
