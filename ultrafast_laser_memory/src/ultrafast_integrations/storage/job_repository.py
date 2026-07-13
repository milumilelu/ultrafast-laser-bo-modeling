from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
import uuid

from ultrafast_agent.jobs.models import BackgroundJob
from ultrafast_memory.db.session import get_connection


class SQLiteJobRepository:
    def create(self, job: BackgroundJob) -> tuple[BackgroundJob, bool]:
        with get_connection() as conn:
            if job.idempotency_key:
                row = conn.execute(
                    "SELECT * FROM background_job WHERE idempotency_key = ?",
                    (job.idempotency_key,),
                ).fetchone()
                if row:
                    return _job(dict(row)), False
            conn.execute(
                """INSERT INTO background_job (
                    job_id, job_type, status, input_json, output_json, progress, current_step,
                    attempt, max_attempts, idempotency_key, timeout_seconds, created_at,
                    started_at, finished_at, heartbeat_at, error_code, error_message
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.job_id, job.job_type, job.status, _dump(job.input), None, job.progress,
                    job.current_step, job.attempt, job.max_attempts, job.idempotency_key,
                    job.timeout_seconds, job.created_at, None, None, None, None, None,
                ),
            )
            conn.commit()
        return job, True

    def get(self, job_id: str) -> BackgroundJob | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM background_job WHERE job_id = ?", (job_id,)).fetchone()
        return _job(dict(row)) if row else None

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM background_job_event WHERE job_id = ? ORDER BY sequence", (job_id,)
            ).fetchall()
        return [{**dict(row), "payload": _load(row["payload_json"], {})} for row in rows]

    def append_event(self, job_id: str, event_type: str, **values: Any) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            sequence = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM background_job_event WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            record = {
                "event_id": f"job_event_{uuid.uuid4().hex}",
                "job_id": job_id,
                "sequence": sequence,
                "event_type": event_type,
                "message": values.get("message"),
                "progress": values.get("progress"),
                "payload_json": _dump(values.get("payload") or {}),
                "created_at": _now(),
            }
            conn.execute(
                "INSERT INTO background_job_event VALUES (:event_id,:job_id,:sequence,:event_type,:message,:progress,:payload_json,:created_at)",
                record,
            )
            conn.commit()
        return {**record, "payload": values.get("payload") or {}}

    def claim_next(self) -> BackgroundJob | None:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM background_job WHERE status IN ('queued','retrying') ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            now = _now()
            changed = conn.execute(
                """UPDATE background_job SET status='running', attempt=attempt+1,
                   started_at=COALESCE(started_at, ?), heartbeat_at=?
                   WHERE job_id=? AND status IN ('queued','retrying')""",
                (now, now, row["job_id"]),
            ).rowcount
            conn.commit()
        return self.get(row["job_id"]) if changed else None

    def update(self, job_id: str, **values: Any) -> BackgroundJob:
        allowed = {
            "status", "output", "progress", "current_step", "attempt", "started_at",
            "finished_at", "heartbeat_at", "error_code", "error_message",
        }
        fields = []
        parameters: list[Any] = []
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f"unsupported job update field: {key}")
            column = "output_json" if key == "output" else key
            fields.append(f"{column} = ?")
            parameters.append(_dump(value) if key == "output" and value is not None else value)
        if fields:
            with get_connection() as conn:
                conn.execute(f"UPDATE background_job SET {', '.join(fields)} WHERE job_id = ?", (*parameters, job_id))
                conn.commit()
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def recover_stale(self, stale_before: str) -> int:
        with get_connection() as conn:
            count = conn.execute(
                """UPDATE background_job SET status='retrying', error_code='worker_restart',
                   error_message='job recovered after stale heartbeat'
                   WHERE status='running' AND heartbeat_at < ? AND attempt < max_attempts""",
                (stale_before,),
            ).rowcount
            conn.execute(
                """UPDATE background_job SET status='failed', error_code='worker_restart',
                   error_message='job exhausted attempts during restart recovery', finished_at=?
                   WHERE status='running' AND heartbeat_at < ? AND attempt >= max_attempts""",
                (_now(), stale_before),
            )
            conn.commit()
        return count


def _job(row: dict[str, Any]) -> BackgroundJob:
    return BackgroundJob(
        job_id=row["job_id"], job_type=row["job_type"], status=row["status"],
        input=_load(row.get("input_json"), {}), output=_load(row.get("output_json"), None),
        progress=float(row.get("progress") or 0), current_step=row.get("current_step"),
        attempt=int(row.get("attempt") or 0), max_attempts=int(row.get("max_attempts") or 3),
        idempotency_key=row.get("idempotency_key"), timeout_seconds=row.get("timeout_seconds"),
        created_at=row.get("created_at"), started_at=row.get("started_at"),
        finished_at=row.get("finished_at"), heartbeat_at=row.get("heartbeat_at"),
        error_code=row.get("error_code"), error_message=row.get("error_message"),
    )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
