from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.schemas import ClarificationContext


class MissingFieldEvaluator:
    @staticmethod
    def evaluate(
        task_spec: dict[str, Any],
        context: ClarificationContext | None = None,
        required_fields: list[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        """Return only an action-scoped gap list; never apply a global process form."""
        required = list(required_fields or (context.pending_fields if context else ()))
        return [field for field in required if task_spec.get(field) is None]


MissingFieldService = MissingFieldEvaluator
