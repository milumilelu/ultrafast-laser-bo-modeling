from __future__ import annotations

from collections.abc import Callable, Iterator

from ultrafast_agent.runtime.event_bus import EventBus
from ultrafast_agent.runtime.execution_context import RunContext
from ultrafast_agent.runtime.tools import ToolRegistry
from ultrafast_agent.runtime.workflow import WorkflowDefinition, WorkflowResult, WorkflowRunner


class AgentRuntime:
    """Single application-facing entry for workflow execution and streaming."""

    def __init__(
        self,
        registry: ToolRegistry,
        event_bus_factory: Callable[[str], EventBus] = EventBus,
    ):
        self._runner = WorkflowRunner(registry, event_bus_factory)

    def execute(self, workflow: WorkflowDefinition, context: RunContext) -> WorkflowResult:
        return self._runner.run(workflow, context)

    def stream(
        self, workflow: WorkflowDefinition, context: RunContext
    ) -> Iterator[dict]:
        yield from self._runner.stream(workflow, context)
