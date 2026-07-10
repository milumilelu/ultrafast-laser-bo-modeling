from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class LegacyCommandDelegates:
    init_task: Callable[..., dict[str, Any]]
    load_task_state: Callable[..., dict[str, Any]]
    save_task_state: Callable[..., None]
    recommend_parameters: Callable[..., dict[str, Any]]
    submit_feedback: Callable[..., dict[str, Any]]
    recommend_next: Callable[..., dict[str, Any]]
    export_task_logs: Callable[..., dict[str, str]]
    run_json: Callable[..., dict[str, Any]]
    feedback_json: Callable[..., dict[str, Any]]


class LegacyCommandCompatibilityService:
    """Stable old-command facade while the BO implementation is migrated incrementally."""

    def __init__(self, delegates: LegacyCommandDelegates):
        self.delegates = delegates

    def init_task(self, *args, **kwargs):
        return self.delegates.init_task(*args, **kwargs)

    def load_task_state(self, *args, **kwargs):
        return self.delegates.load_task_state(*args, **kwargs)

    def save_task_state(self, *args, **kwargs):
        return self.delegates.save_task_state(*args, **kwargs)

    def recommend_parameters(self, *args, **kwargs):
        return self.delegates.recommend_parameters(*args, **kwargs)

    def submit_feedback(self, *args, **kwargs):
        return self.delegates.submit_feedback(*args, **kwargs)

    def recommend_next(self, *args, **kwargs):
        return self.delegates.recommend_next(*args, **kwargs)

    def export_task_logs(self, *args, **kwargs):
        return self.delegates.export_task_logs(*args, **kwargs)

    def run_json(self, *args, **kwargs):
        return self.delegates.run_json(*args, **kwargs)

    def feedback_json(self, *args, **kwargs):
        return self.delegates.feedback_json(*args, **kwargs)
