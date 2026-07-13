from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Protocol
import uuid

from ultrafast_agent.jobs.models import BackgroundJob, JobStatus, TERMINAL_JOB_STATUSES


class JobRepository(Protocol):
    def create(self, job: BackgroundJob) -> tuple[BackgroundJob, bool]: ...
    def get(self, job_id: str) -> BackgroundJob | None: ...
    def list_events(self, job_id: str) -> list[dict[str, Any]]: ...
    def append_event(self, job_id: str, event_type: str, **values: Any) -> dict[str, Any]: ...
    def claim_next(self) -> BackgroundJob | None: ...
    def update(self, job_id: str, **values: Any) -> BackgroundJob: ...
    def recover_stale(self, stale_before: str) -> int: ...


class BackgroundJobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    def create(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        timeout_seconds: float | None = None,
    ) -> tuple[BackgroundJob, bool]:
        if not job_type.strip():
            raise ValueError("job_type is required")
        job = BackgroundJob(
            job_id=f"job_{uuid.uuid4().hex}",
            job_type=job_type,
            status=JobStatus.QUEUED.value,
            input=dict(payload),
            max_attempts=max(1, max_attempts),
            idempotency_key=idempotency_key,
            timeout_seconds=timeout_seconds,
            created_at=_now(),
        )
        stored, created = self.repository.create(job)
        if created:
            self.repository.append_event(stored.job_id, "job_created", message="job queued", progress=0.0)
        return stored, created

    def get(self, job_id: str) -> BackgroundJob:
        job = self.repository.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def cancel(self, job_id: str) -> BackgroundJob:
        job = self.get(job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        status = JobStatus.CANCELLED.value if job.status in {"queued", "retrying"} else JobStatus.CANCEL_REQUESTED.value
        updated = self.repository.update(job_id, status=status, finished_at=_now() if status == "cancelled" else None)
        self.repository.append_event(job_id, "cancel_requested", message="cancellation requested", progress=updated.progress)
        return updated

    def retry(self, job_id: str) -> BackgroundJob:
        job = self.get(job_id)
        if job.status not in {"failed", "timed_out", "cancelled"}:
            raise ValueError("only failed, timed_out, or cancelled jobs can be retried")
        updated = self.repository.update(
            job_id,
            status=JobStatus.RETRYING.value,
            error_code=None,
            error_message=None,
            finished_at=None,
        )
        self.repository.append_event(job_id, "job_retrying", message="job queued for retry", progress=updated.progress)
        return updated


@dataclass(slots=True)
class JobExecutionContext:
    job_id: str
    repository: JobRepository

    def cancelled(self) -> bool:
        job = self.repository.get(self.job_id)
        return bool(job and job.status == JobStatus.CANCEL_REQUESTED.value)

    def progress(self, value: float, step: str, payload: dict[str, Any] | None = None) -> None:
        bounded = max(0.0, min(1.0, float(value)))
        self.repository.update(self.job_id, progress=bounded, current_step=step, heartbeat_at=_now())
        self.repository.append_event(
            self.job_id,
            "job_progressed",
            message=step,
            progress=bounded,
            payload=payload or {},
        )


JobHandler = Callable[[dict[str, Any], JobExecutionContext], dict[str, Any] | None]


class JobWorker:
    def __init__(self, repository: JobRepository, handlers: dict[str, JobHandler] | None = None):
        self.repository = repository
        self.handlers = dict(handlers or {})

    def register(self, job_type: str, handler: JobHandler) -> None:
        self.handlers[job_type] = handler

    def run_once(self) -> BackgroundJob | None:
        job = self.repository.claim_next()
        if job is None:
            return None
        handler = self.handlers.get(job.job_type)
        if handler is None:
            return self._fail(job, "validation_failed", f"unregistered job type: {job.job_type}", retryable=False)
        context = JobExecutionContext(job.job_id, self.repository)
        started = time.monotonic()
        self.repository.append_event(job.job_id, "job_started", message="worker claimed job", progress=job.progress)
        try:
            output = handler(job.input, context) or {}
            current = self.repository.get(job.job_id)
            if current and current.status == JobStatus.CANCEL_REQUESTED.value:
                updated = self.repository.update(job.job_id, status="cancelled", finished_at=_now())
                self.repository.append_event(job.job_id, "job_cancelled", message="job cancelled", progress=updated.progress)
                return updated
            if job.timeout_seconds is not None and time.monotonic() - started > job.timeout_seconds:
                updated = self.repository.update(
                    job.job_id,
                    status="timed_out",
                    error_code="timeout",
                    error_message="job exceeded timeout",
                    finished_at=_now(),
                )
                self.repository.append_event(job.job_id, "job_timed_out", message=updated.error_message, progress=updated.progress)
                return updated
            updated = self.repository.update(
                job.job_id,
                status="succeeded",
                output=output,
                progress=1.0,
                current_step="completed",
                heartbeat_at=_now(),
                finished_at=_now(),
            )
            self.repository.append_event(job.job_id, "job_succeeded", message="job completed", progress=1.0)
            return updated
        except Exception as exc:  # noqa: BLE001 - persisted application boundary
            retryable = bool(getattr(exc, "retryable", False))
            return self._fail(job, str(getattr(exc, "code", "job_failed")), str(exc), retryable=retryable)

    def _fail(self, job: BackgroundJob, code: str, message: str, *, retryable: bool) -> BackgroundJob:
        current = self.repository.get(job.job_id) or job
        should_retry = retryable and current.attempt < current.max_attempts
        status = "retrying" if should_retry else "failed"
        updated = self.repository.update(
            job.job_id,
            status=status,
            error_code=code,
            error_message=message,
            heartbeat_at=_now(),
            finished_at=None if should_retry else _now(),
        )
        self.repository.append_event(job.job_id, f"job_{status}", message=message, progress=updated.progress)
        return updated


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

