from __future__ import annotations

from threading import Event


class WorkflowCancelled(RuntimeError):
    """Raised when a caller cancels a running workflow."""


class CancellationToken:
    def __init__(self):
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()
