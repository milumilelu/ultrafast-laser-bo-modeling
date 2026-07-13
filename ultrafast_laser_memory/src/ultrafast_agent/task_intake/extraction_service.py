from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.candidate_resolver import TaskFieldCandidateResolver
from ultrafast_agent.task_intake.deterministic_extractor import ContextualDeterministicExtractor
from ultrafast_agent.task_intake.llm_extractor import LLMTaskFieldExtractor
from ultrafast_agent.task_intake.schemas import ClarificationContext, TaskSpecPatch


class HybridTaskFieldExtractionService:
    def __init__(self, llm_client: Any | None = None):
        self.deterministic = ContextualDeterministicExtractor()
        self.llm = LLMTaskFieldExtractor(llm_client)

    def extract(
        self,
        message: str,
        current_spec: dict[str, Any],
        context: ClarificationContext,
    ) -> TaskSpecPatch:
        deterministic = self.deterministic.extract(message, current_spec, context)
        patches = [deterministic]
        if self._needs_llm(message, deterministic, context):
            patches.append(self.llm.extract(message, current_spec, context))
        return TaskFieldCandidateResolver.resolve(patches)

    @staticmethod
    def _needs_llm(
        message: str,
        deterministic: TaskSpecPatch,
        context: ClarificationContext,
    ) -> bool:
        if deterministic.ambiguities:
            return True
        if context.pending_fields and not deterministic.updates and message.strip():
            return True
        correction = any(marker in message for marker in ("改为", "修改为", "更正为", "纠正为", "不是", "应为"))
        if correction and not any(item.operation == "correct" for item in deterministic.updates):
            return True
        return False
