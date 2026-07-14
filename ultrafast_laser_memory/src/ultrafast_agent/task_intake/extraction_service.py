from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.llm_extractor import LLMStructuredExtractor
from ultrafast_agent.task_intake.schemas import ClarificationContext, TaskSpecPatch
from ultrafast_agent.task_intake.strict_key_value_parser import StrictKeyValueParser


class TaskFieldExtractionService:
    def __init__(self, llm_client: Any | None = None):
        self.strict_parser = StrictKeyValueParser()
        self.llm = LLMStructuredExtractor(llm_client)

    def extract(
        self,
        message: str,
        current_spec: dict[str, Any],
        context: ClarificationContext,
    ) -> TaskSpecPatch:
        strict = self.strict_parser.parse(message, context)
        if strict is not None:
            return strict
        return self.llm.extract(message, current_spec, context)


# Import compatibility only; the implementation is now LLM-first.
HybridTaskFieldExtractionService = TaskFieldExtractionService
