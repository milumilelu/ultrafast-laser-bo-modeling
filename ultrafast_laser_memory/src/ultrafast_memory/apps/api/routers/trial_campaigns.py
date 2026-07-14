from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/v1/trial-campaigns", tags=["trial-campaigns"])


class CampaignCreateRequest(BaseModel):
    task_id: str
    workflow_id: str
    task_spec: dict[str, Any]
    search_space: dict[str, Any]
    current_recipe: dict[str, Any]
    parameter_units: dict[str, str]
    equipment_revision: str
    targets: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class StrategySelectRequest(BaseModel):
    strategy: str
    recommendation_options: dict[str, dict[str, Any]]


class FeedbackRequest(BaseModel):
    run_id: str
    cam_applied_parameters: dict[str, Any]
    machine_actual_parameters: dict[str, Any]
    measurements: dict[str, Any]
    parameter_units: dict[str, str]
    measurement_units: dict[str, str]
    constraint_results: dict[str, bool] = Field(default_factory=dict)
    run_status: str = "completed"
    alarms: list[str] = Field(default_factory=list)
    measurement_method: str
    material: str
    process_type: str
    equipment_revision: str
    risk_state: str = "normal"


class AdvanceRequest(BaseModel):
    approved_by: str
    next_bo_result: dict[str, Any] | None = None


class ApprovalRequest(BaseModel):
    approved_by: str


class FinalInspectionRequest(BaseModel):
    measurements: dict[str, Any]
    constraint_results: dict[str, bool]
    files: list[str] = Field(default_factory=list)


def _service():
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.trial.closed_loop import TrialClosedLoopService

    init_database()
    return TrialClosedLoopService()


def _run(call):
    try:
        return call()
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "validation_failed", "message": str(exc)}) from exc


@router.post("")
def create_campaign(request: CampaignCreateRequest) -> dict[str, Any]:
    return _run(lambda: _service().create_campaign(**request.model_dump()))


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str) -> dict[str, Any]:
    return _run(lambda: _service().get_campaign(campaign_id))


@router.post("/{campaign_id}/strategy")
def select_strategy(campaign_id: str, request: StrategySelectRequest) -> dict[str, Any]:
    return _run(lambda: _service().select_strategy(
        campaign_id, request.strategy, request.recommendation_options
    ))


@router.post("/{campaign_id}/recommendations/{recommendation_id}/feedback")
def submit_feedback(
    campaign_id: str, recommendation_id: str, request: FeedbackRequest
) -> dict[str, Any]:
    return _run(lambda: _service().submit_feedback(
        campaign_id, recommendation_id, request.model_dump()
    ))


@router.post("/{campaign_id}/observations/{observation_id}/approve-and-advance")
def approve_feedback_and_advance(
    campaign_id: str, observation_id: str, request: AdvanceRequest
) -> dict[str, Any]:
    return _run(lambda: _service().approve_feedback_and_advance(
        campaign_id,
        observation_id,
        approved_by=request.approved_by,
        next_bo_result=request.next_bo_result,
    ))


@router.post("/{campaign_id}/production/{candidate_id}/approve")
def approve_production(
    campaign_id: str, candidate_id: str, request: ApprovalRequest
) -> dict[str, Any]:
    return _run(lambda: _service().approve_production(
        campaign_id, candidate_id, approved_by=request.approved_by
    ))


@router.post("/{campaign_id}/external-processing")
def report_external_processing(campaign_id: str) -> dict[str, Any]:
    return _run(lambda: _service().report_external_processing_started(campaign_id))


@router.post("/{campaign_id}/final-inspection")
def submit_final_inspection(
    campaign_id: str, request: FinalInspectionRequest
) -> dict[str, Any]:
    return _run(lambda: _service().submit_final_inspection(
        campaign_id,
        measurements=request.measurements,
        constraint_results=request.constraint_results,
        files=request.files,
    ))
