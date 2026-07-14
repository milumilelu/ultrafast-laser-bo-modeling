from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.schemas import ClarificationContext, PROCESS_REQUIRED_FIELDS


class MissingFieldEvaluator:
    @staticmethod
    def evaluate(task_spec: dict[str, Any], context: ClarificationContext | None = None) -> list[str]:
        if context and context.workflow_type != "complex_process_task":
            return []
        return [field for field in PROCESS_REQUIRED_FIELDS if task_spec.get(field) is None]


MissingFieldService = MissingFieldEvaluator
