from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Any

from ultrafast_agent.runtime.event_bus import EventBus
from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_agent.runtime.sinks import DatabaseEventSink
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository


class AgentEventService:
    """Single event creation and sequence authority for application events."""

    def __init__(self, repository: RuntimeEventRepository | None = None, max_active_runs: int = 256):
        self.repository = repository or RuntimeEventRepository()
        self.database_sink = DatabaseEventSink(self.repository)
        self.max_active_runs = max_active_runs
        self._buses: OrderedDict[str, EventBus] = OrderedDict()
        self._lock = Lock()

    def emit(
        self,
        *,
        run_id: str,
        session_id: str | None,
        message_id: str | None,
        workflow_id: str | None,
        event_type: str,
        stage: str,
        title: str,
        public_summary: str,
        status: str,
        progress: int | None = None,
        skill: str | None = None,
        tool: str | None = None,
        step: str | None = None,
        payload: dict[str, Any] | None = None,
        visibility: str = "public",
        idempotency_key: str | None = None,
    ) -> AgentEvent:
        bus = self._bus(run_id, session_id)
        return bus.emit(
            event_type,
            stage=stage,
            title=title,
            summary=public_summary,
            status=status,
            progress=progress,
            skill=skill,
            tool=tool,
            step=step,
            workflow_id=workflow_id,
            message_id=message_id,
            data=payload,
            visibility=visibility,
            idempotency_key=idempotency_key,
        )

    def _bus(self, run_id: str, session_id: str | None) -> EventBus:
        with self._lock:
            bus = self._buses.get(run_id)
            if bus is not None:
                self._buses.move_to_end(run_id)
                return bus
            bus = EventBus(
                run_id,
                session_id=session_id,
                initial_sequence=self.repository.max_sequence(run_id),
            )
            bus.subscribe(self.database_sink.append)
            self._buses[run_id] = bus
            while len(self._buses) > self.max_active_runs:
                self._buses.popitem(last=False)
            return bus


canonical_agent_events = AgentEventService()
