from __future__ import annotations

from threading import Lock

from ultrafast_agent.runtime.events import AgentEvent


class TraceCollector:
    """Thread-safe in-memory collector; durable storage remains an adapter concern."""

    def __init__(self):
        self._events: list[AgentEvent] = []
        self._lock = Lock()

    def record(self, event: AgentEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [event.to_dict() for event in self._events]
