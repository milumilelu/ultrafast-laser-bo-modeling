from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ultrafast_agent.jobs import BackgroundJobService
from ultrafast_integrations.storage.job_repository import SQLiteJobRepository
from ultrafast_memory.db.init_db import init_database


router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    job_type: str
    input: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    max_attempts: int = 3
    timeout_seconds: float | None = None


def _service() -> BackgroundJobService:
    init_database()
    return BackgroundJobService(SQLiteJobRepository())


@router.post("")
def create_job(request: CreateJobRequest) -> dict[str, Any]:
    job, created = _service().create(
        request.job_type, request.input, idempotency_key=request.idempotency_key,
        max_attempts=request.max_attempts, timeout_seconds=request.timeout_seconds,
    )
    return {**job.to_dict(), "created": created}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return _service().get(job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "job_not_found", "message": "job not found"}) from exc


@router.get("/{job_id}/events")
def get_job_events(job_id: str) -> dict[str, Any]:
    try:
        _service().get(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "job_not_found", "message": "job not found"}) from exc
    return {"job_id": job_id, "events": SQLiteJobRepository().list_events(job_id)}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        return _service().cancel(job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "job_not_found", "message": "job not found"}) from exc


@router.post("/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    try:
        return _service().retry(job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "job_not_found", "message": "job not found"}) from exc
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "invalid_job_state", "message": str(exc)}) from exc

