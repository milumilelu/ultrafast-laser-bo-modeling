from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
    JobStatus.TIMED_OUT.value,
}


@dataclass(slots=True)
class BackgroundJob:
    job_id: str
    job_type: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    progress: float = 0.0
    current_step: str | None = None
    attempt: int = 0
    max_attempts: int = 3
    idempotency_key: str | None = None
    timeout_seconds: float | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    heartbeat_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BackgroundJobEvent:
    event_id: str
    job_id: str
    sequence: int
    event_type: str
    message: str | None = None
    progress: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

