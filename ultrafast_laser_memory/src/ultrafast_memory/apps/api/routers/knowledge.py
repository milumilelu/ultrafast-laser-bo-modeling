from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest, EvidenceGapRequest
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest
from ultrafast_memory.knowledge_use.schemas import (
    KnowledgeApprovalRevokeRequest,
    KnowledgeUseActionRequest,
    KnowledgeUseEvaluateRequest,
)


router = APIRouter(tags=["knowledge"])


def _usage_service():
    from ultrafast_memory.knowledge_use.service import KnowledgeUseApplicationService

    return KnowledgeUseApplicationService()


class ReviewRequest(BaseModel):
    action: str
    comment: str = ""


@router.get("/experience/candidates")
def candidates(status: str = "candidate") -> list[dict]:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge.review_queue import list_candidates

    init_database()
    return list_candidates(status)


@router.post("/experience/candidates/{candidate_id}/review")
def review_candidate(candidate_id: str, request: ReviewRequest) -> dict:
    from ultrafast_memory.knowledge.review_queue import (
        accept_candidate,
        mark_needs_more_evidence,
        reject_candidate,
    )

    actions = {
        "accept": accept_candidate,
        "reject": reject_candidate,
        "needs_more_evidence": mark_needs_more_evidence,
    }
    if request.action not in actions:
        raise HTTPException(status_code=400, detail="invalid action")
    actions[request.action](candidate_id, request.comment)
    return {"candidate_id": candidate_id, "status": request.action}


@router.post("/knowledge/evidence-gap")
def knowledge_evidence_gap(request: EvidenceGapRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_bootstrap.service import check_evidence_gap

    init_database()
    return check_evidence_gap(request).model_dump(mode="json")


@router.post("/knowledge/bootstrap-web")
def knowledge_bootstrap_web(request: BootstrapWebRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_bootstrap.service import bootstrap_from_web

    init_database()
    return bootstrap_from_web(request).model_dump(mode="json")


@router.get("/knowledge/candidates")
def knowledge_candidates(status: str = "pending_review") -> list[dict]:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_review.service import list_candidates

    init_database()
    return list_candidates(status)


@router.get("/knowledge/review/tasks")
def knowledge_review_tasks(status: str = "pending_review") -> list[dict]:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_review.service import list_tasks

    init_database()
    return list_tasks(status)


@router.get("/knowledge/review/tasks/{review_id}")
def knowledge_review_task(review_id: str) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_review.service import get_task

    init_database()
    try:
        return get_task(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge/review/tasks/{review_id}/action")
def knowledge_review_action(review_id: str, request: ReviewActionRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_review.service import apply_action

    init_database()
    try:
        return apply_action(review_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/knowledge/use-gate")
def knowledge_use_gate_evaluate(task_id: str, request: KnowledgeUseEvaluateRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database

    init_database()
    try:
        return _usage_service().evaluate(task_id, request.model_dump(mode="json"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge/usage-decisions/{decision_id}")
def knowledge_usage_decision_get(decision_id: str) -> dict:
    try:
        return _usage_service().get_decision(decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge/usage-decisions/{decision_id}/approve-task")
def knowledge_usage_decision_approve_task(
    decision_id: str, request: KnowledgeUseActionRequest
) -> dict:
    try:
        return _usage_service().approve_task(decision_id, request.model_dump(mode="json"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/usage-decisions/{decision_id}/approve-prior")
def knowledge_usage_decision_approve_prior(
    decision_id: str, request: KnowledgeUseActionRequest
) -> dict:
    try:
        return _usage_service().approve_prior(decision_id, request.model_dump(mode="json"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/usage-decisions/{decision_id}/reject")
def knowledge_usage_decision_reject(
    decision_id: str, request: KnowledgeUseActionRequest
) -> dict:
    try:
        return _usage_service().reject(decision_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/usage-approvals/{approval_id}/revoke")
def knowledge_usage_approval_revoke(
    approval_id: str, request: KnowledgeApprovalRevokeRequest
) -> dict:
    try:
        return _usage_service().revoke(approval_id, request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
