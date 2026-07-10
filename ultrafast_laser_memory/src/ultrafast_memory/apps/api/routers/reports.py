from fastapi import APIRouter, HTTPException

from ultrafast_memory.reports.schemas import TaskReportGenerateRequest
router = APIRouter(tags=["reports"])


def _service():
    from ultrafast_memory.reports.task_report_service import TaskReportService

    return TaskReportService()


@router.post("/tasks/{task_id}/reports")
def task_report_generate(task_id: str, request: TaskReportGenerateRequest) -> dict:
    return _service().generate(task_id, request.payload, request.run_id)


@router.get("/tasks/{task_id}/reports/latest")
def task_report_latest(task_id: str) -> dict:
    try:
        return _service().get_latest(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
