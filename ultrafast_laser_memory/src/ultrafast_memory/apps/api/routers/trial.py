from fastapi import APIRouter, HTTPException

from ultrafast_memory.trial.schemas import (
    TrialAssessRequest,
    TrialEvaluateRequest,
    TrialExecutionCreateRequest,
    TrialPlanCreateRequest,
    TrialResultCreateRequest,
    TrialSelectRequest,
)
router = APIRouter(tags=["trial"])


def _service():
    from ultrafast_memory.trial.service import TrialApplicationService

    return TrialApplicationService()


@router.post("/tasks/{task_id}/trial/assess")
def trial_assess(task_id: str, request: TrialAssessRequest) -> dict:
    return _service().assess(task_id, request.model_dump(mode="json"))


@router.post("/tasks/{task_id}/trial/select")
def trial_select(task_id: str, request: TrialSelectRequest) -> dict:
    try:
        return _service().select(task_id, request.assessment, request.trial_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/trial/plans")
def trial_plan_create(task_id: str, request: TrialPlanCreateRequest) -> dict:
    try:
        return _service().create_plan(task_id, request.model_dump(mode="json"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trial/plans/{trial_plan_id}")
def trial_plan_get(trial_plan_id: str) -> dict:
    try:
        return _service().get_plan(trial_plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trial/plans/{trial_plan_id}/executions")
def trial_execution_create(
    trial_plan_id: str, request: TrialExecutionCreateRequest
) -> dict:
    try:
        return _service().start_execution(trial_plan_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/trial/executions/{execution_id}/results")
def trial_result_create(execution_id: str, request: TrialResultCreateRequest) -> dict:
    try:
        return _service().create_result(execution_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/trial/results/{result_id}/evaluate")
def trial_result_evaluate(result_id: str, request: TrialEvaluateRequest) -> dict:
    try:
        return _service().evaluate(result_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
