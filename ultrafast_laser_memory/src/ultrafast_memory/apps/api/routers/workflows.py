from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ultrafast_agent.observability import normalize_stream_event
from ultrafast_memory.workflows.schemas import WorkflowExecuteRequest


router = APIRouter(tags=["workflows"])


def _service():
    from ultrafast_memory.workflows.service import TaskWorkflowService

    return TaskWorkflowService()


@router.post("/workflows/{workflow_name}/execute")
def workflow_execute(workflow_name: str, request: WorkflowExecuteRequest) -> dict:
    try:
        return _service().execute(workflow_name, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workflows/{workflow_name}/stream_ndjson")
def workflow_stream(
    workflow_name: str, request: WorkflowExecuteRequest
) -> StreamingResponse:
    def iter_lines():
        try:
            for event in _service().stream(
                workflow_name, request.model_dump(mode="json")
            ):
                normalized = normalize_stream_event(
                    event, int(event["sequence"]), request.display_mode
                )
                if normalized is not None:
                    yield json.dumps(normalized, ensure_ascii=False) + "\n"
        except ValueError as exc:
            event = normalize_stream_event(
                {
                    "type": "error",
                    "event_type": "error",
                    "stage": "workflow",
                    "summary": str(exc),
                    "status": "failed",
                },
                1,
                request.display_mode,
            )
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(iter_lines(), media_type="application/x-ndjson")


@router.get("/execution-traces/{run_id}")
def execution_trace_get(run_id: str) -> dict:
    return {"run_id": run_id, "events": _service().get_trace(run_id)}
