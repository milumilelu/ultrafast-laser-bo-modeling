from __future__ import annotations

from typing import Protocol

from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository


class AgentEventSink(Protocol):
    def append(self, event: AgentEvent) -> None: ...


class DatabaseEventSink:
    def __init__(self, repository: RuntimeEventRepository | None = None):
        self.repository = repository or RuntimeEventRepository()

    def append(self, event: AgentEvent) -> None:
        self.repository.persist(event)


class InMemoryTraceSink:
    def __init__(self):
        self.events: list[AgentEvent] = []

    def append(self, event: AgentEvent) -> None:
        self.events.append(event)
