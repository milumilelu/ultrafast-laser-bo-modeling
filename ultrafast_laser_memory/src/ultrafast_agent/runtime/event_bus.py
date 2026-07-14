from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from ultrafast_agent.runtime.events import AgentEvent, redact_public_data


Subscriber = Callable[[AgentEvent], None]


class EventBus:
    def __init__(
        self,
        run_id: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        trace_id: str | None = None,
        initial_sequence: int = 0,
    ):
        self.run_id = run_id
        self.session_id = session_id
        self.task_id = task_id
        self.trace_id = trace_id or run_id
        self._sequence = initial_sequence
        self._events: list[AgentEvent] = []
        self._subscribers: list[Subscriber] = []
        self._lock = Lock()

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    def emit(
        self,
        event_type: str,
        *,
        stage: str,
        title: str,
        summary: str,
        status: str,
        progress: int | None = None,
        skill: str | None = None,
        tool: str | None = None,
        duration_ms: float | None = None,
        cache_hit: bool | None = None,
        attempt: int | None = None,
        data: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
        visibility: str = "public",
        evidence_refs: list[str] | None = None,
        workflow_id: str | None = None,
        message_id: str | None = None,
        step: str | None = None,
        idempotency_key: str | None = None,
    ) -> AgentEvent:
        with self._lock:
            self._sequence += 1
            safe_data = redact_public_data(data or {})
            event = AgentEvent(
                run_id=self.run_id,
                stream_id=self.run_id,
                idempotency_key=idempotency_key,
                trace_id=self.trace_id,
                session_id=self.session_id,
                workflow_id=workflow_id,
                message_id=message_id,
                task_id=self.task_id,
                sequence=self._sequence,
                event_type=event_type,
                stage=stage,
                title=title,
                summary=summary,
                status=status,
                progress=progress,
                skill=skill,
                step=step,
                tool=tool,
                duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
                cache_hit=cache_hit,
                attempt=attempt,
                input_summary=_as_summary(safe_data.get("input_summary")),
                output_summary=_as_summary(safe_data.get("output_summary")),
                evidence_refs=list(evidence_refs or []),
                parent_event_id=parent_event_id,
                visibility=visibility,
                data=safe_data,
                public_summary=summary,
                payload=safe_data,
            )
            self._events.append(event)
            subscribers = tuple(self._subscribers)
            # Delivery shares the sequence lock so concurrent tools cannot reorder
            # persisted or streamed events after a sequence number is assigned.
            for subscriber in subscribers:
                subscriber(event)
        return event

    @property
    def events(self) -> list[AgentEvent]:
        with self._lock:
            return list(self._events)


def _as_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    return value if isinstance(value, dict) else {"summary": str(value)}
