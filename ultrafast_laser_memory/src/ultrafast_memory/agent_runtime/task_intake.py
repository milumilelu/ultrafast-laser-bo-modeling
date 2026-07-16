from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TASK_INTAKE_VERSION = "llm-first-v1"


@dataclass(slots=True)
class TaskIntakeResult:
    """Non-authoritative preparation for LLM-first task understanding.

    Task Intake deliberately does not classify materials, geometry, process
    intent, missing fields, or corrections. Those semantics belong to the
    Main LLM under the task_understanding Skill. This object only records that
    the message is ready for that step and supplies non-binding Skill hints.
    """

    context_updates: dict[str, Any] = field(default_factory=dict)
    skill_hints: list[str] = field(default_factory=lambda: ["task_understanding"])
    changed_fields: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    blocking_fields: list[str] = field(default_factory=list)
    summary: str = "用户原文已交给 Main LLM 进行任务理解；规则未写入任何领域事实。"


class HybridTaskFieldExtractionService:
    """Compatibility entrypoint whose semantics are now LLM-first.

    The historical class name is retained for callers, but it no longer acts
    as a regex-based domain parser or a source of canonical task facts.
    """

    def prepare(self, message: str, working_context: dict[str, Any]) -> TaskIntakeResult:
        del message, working_context
        return TaskIntakeResult(
            context_updates={
                "task_intake": {
                    "extractor": TASK_INTAKE_VERSION,
                    "authority": "hint_only",
                    "changed_fields": [],
                    "field_provenance": {},
                    "conflicts": [],
                    "ambiguities": [],
                    "blocking_fields": [],
                },
            },
        )


def prepare_task_context(message: str, working_context: dict[str, Any]) -> TaskIntakeResult:
    return HybridTaskFieldExtractionService().prepare(message, working_context)
