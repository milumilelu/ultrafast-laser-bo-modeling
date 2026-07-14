"""Read-only workflow projection public surface.

Business transitions, message parsing, event creation, and persistence do not
live here. Legacy imports are re-exported from an explicitly named adapter.
"""

from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.missing_field_service import MissingFieldEvaluator
from ultrafast_memory.chat.legacy_projection_adapter import (
    get_latest_progress,
    list_public_thinking_status,
    mark_workflow_completed,
    record_public_trace,
    upsert_workflow_progress,
)
from ultrafast_memory.chat.workflow_projection import (
    WorkflowProjection,
    WorkflowProjectionService,
)


def missing_process_fields(task_spec: dict[str, Any]) -> list[str]:
    return MissingFieldEvaluator.evaluate(task_spec)


__all__ = [
    "WorkflowProjection",
    "WorkflowProjectionService",
    "get_latest_progress",
    "list_public_thinking_status",
    "mark_workflow_completed",
    "missing_process_fields",
    "record_public_trace",
    "upsert_workflow_progress",
]
