from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ultrafast_memory.process_workflow.closure import archive_gate, bo_sample_eligibility, quality_decision
from ultrafast_memory.process_workflow.policy import formal_release_gate
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.process_workflow.repository import ProcessWorkflowRepository
from ultrafast_memory.process_workflow.campaign import CampaignService
from ultrafast_memory.reports.task_report_service import TaskReportService


router = APIRouter(tags=["process-workflow-v3"])


def _repository() -> ProcessWorkflowRepository:
    return ProcessWorkflowRepository()


@router.post("/process-workflow/formal/release-gate")
def release_gate(payload: dict) -> dict:
    allowed, reasons = formal_release_gate(
        trial_passed=bool(payload.get("trial_passed")), source_types=payload.get("source_types") or [],
        equipment_revision_matches=bool(payload.get("equipment_revision_matches")),
        preflight_complete=bool(payload.get("preflight_complete")),
    )
    return {"unlocked": allowed, "decision": "released" if allowed else "blocked", "reasons": reasons}


@router.post("/process-workflow/inspection/decision")
def inspection_decision(payload: dict) -> dict:
    return quality_decision(payload.get("required_metrics") or [], payload.get("measurements") or {},
                            payload.get("constraint_results") or {})


@router.post("/process-workflow/bo/eligibility")
def eligibility(payload: dict) -> dict:
    return bo_sample_eligibility(payload)


@router.post("/process-workflow/archive-gate")
def task_archive_gate(payload: dict) -> dict:
    allowed, missing = archive_gate(quality_decided=bool(payload.get("quality_decided")),
        report_generated=bool(payload.get("report_generated")),
        experiment_record_validated=bool(payload.get("experiment_record_validated")))
    if not allowed:
        raise HTTPException(status_code=409, detail={"status": "blocked", "missing": missing})
    return {"status": "ready_to_archive", "allowed": True}


@router.post("/process-workflow/formal/local-adjustment")
def formal_local_adjustment(payload: dict) -> dict:
    region = CampaignService.local_trust_region(
        payload.get("approved_window") or {}, payload.get("equipment_bounds") or {},
        payload.get("local_trust_region") or {})
    proposed = payload.get("proposed_parameters") or {}
    violations = [name for name, value in proposed.items()
                  if name not in region or not region[name][0] <= float(value) <= region[name][1]]
    return {"allowed": not violations and bool(proposed), "effective_trust_region": region,
            "violations": violations, "decision": "allowed" if not violations and proposed else "blocked"}


@router.post("/tasks/{task_id}/formal-process/release")
def formal_release(task_id: str, payload: dict) -> dict:
    allowed, reasons = formal_release_gate(trial_passed=bool(payload.get("trial_passed")),
        source_types=payload.get("source_types") or [],
        equipment_revision_matches=bool(payload.get("equipment_revision_matches")),
        preflight_complete=True)
    plan_id = stable_id("formal-plan", task_id, str(payload.get("trial_result_id")))
    record = {"plan_id": plan_id, "task_id": task_id, "release_status": "released" if allowed else "blocked",
              "reasons": reasons, "equipment_revision": payload.get("equipment_revision"),
              "trial_result_id": payload.get("trial_result_id"),
              "parameter_recommendation_id": payload.get("parameter_recommendation_id"),
              "approved_window": payload.get("approved_window") or {}, "toolpath": payload.get("toolpath") or {},
              "monitoring_plan": payload.get("monitoring_plan") or {},
              "stop_conditions": payload.get("stop_conditions") or [], "created_at": utc_now_iso()}
    return _repository().save_plan(record)


@router.post("/tasks/{task_id}/formal-process/preflight")
def formal_preflight(task_id: str, payload: dict) -> dict:
    required = ["plan_id", "equipment_revision", "material_batch", "operator_confirmation"]
    missing = [key for key in required if not payload.get(key)]
    plan = _repository().get_plan(payload.get("plan_id"))
    if not plan or plan.get("task_id") != task_id:
        missing.append("released_plan")
    if plan and plan.get("equipment_revision") != payload.get("equipment_revision"):
        missing.append("equipment_revision_match")
    status = "passed" if not missing else "blocked"
    if plan and status == "passed":
        _repository().set_plan_status(plan["plan_id"], "preflight_passed")
    return {"task_id": task_id, "plan_id": payload.get("plan_id"), "status": status, "missing": missing}


@router.post("/tasks/{task_id}/formal-process/start")
def formal_start(task_id: str, payload: dict) -> dict:
    if payload.get("preflight_status") != "passed":
        raise HTTPException(status_code=409, detail="preflight_not_passed")
    execution_id = stable_id("formal-exec", task_id, utc_now_iso())
    plan = _repository().get_plan(payload.get("plan_id"))
    if not plan or plan.get("task_id") != task_id or plan.get("release_status") != "preflight_passed":
        raise HTTPException(status_code=409, detail="released_plan_preflight_not_found")
    record = {"execution_id": execution_id, "task_id": task_id, "plan_id": payload.get("plan_id"),
              "actual_parameters": payload.get("actual_parameters") or {}, "actual_path": payload.get("actual_path") or {},
              "status": "running", "runtime_log": {"progress_percent": 0, "checkpoints": []},
              "started_at": utc_now_iso(), "finished_at": None}
    _repository().save_execution(record)
    return _present_execution(record)


def _execution(execution_id: str) -> dict:
    record = _repository().get_execution(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail="execution_not_found")
    return record


def _present_execution(record: dict) -> dict:
    runtime = record.get("runtime_log") or {}
    return {**record, "progress_percent": runtime.get("progress_percent", 0),
            "checkpoints": runtime.get("checkpoints", [])}


@router.post("/formal-process/executions/{execution_id}/progress")
def formal_progress(execution_id: str, payload: dict) -> dict:
    record = _execution(execution_id)
    runtime = record.get("runtime_log") or {}
    current = float(runtime.get("progress_percent", 0))
    value = float(payload.get("progress_percent", current))
    if value < current or not 0 <= value <= 100:
        raise HTTPException(status_code=409, detail="non_monotonic_progress")
    runtime["progress_percent"] = value
    record["runtime_log"] = runtime
    return _present_execution(_repository().update_execution(record))


@router.post("/formal-process/executions/{execution_id}/checkpoints")
def checkpoint(execution_id: str, payload: dict) -> dict:
    record = _execution(execution_id)
    level = int(payload.get("deviation_level", 0))
    decision = "abort_return_to_trial" if level >= 3 else "pause_for_confirmation" if level == 2 else "continue"
    runtime = record.get("runtime_log") or {}
    checkpoints = runtime.get("checkpoints") or []
    item = {"checkpoint_id": stable_id("checkpoint", execution_id, str(len(checkpoints))),
            "execution_id": execution_id, "checkpoint_type": payload.get("checkpoint_type", "runtime"),
            "progress_percent": payload.get("progress_percent", runtime.get("progress_percent", 0)),
            "decision": decision, "observation": payload, "created_at": utc_now_iso()}
    checkpoints.append(item)
    runtime["checkpoints"] = checkpoints
    record["runtime_log"] = runtime
    if level >= 2:
        record["status"] = "paused" if level == 2 else "aborted"
    _repository().save_checkpoint(item)
    _repository().update_execution(record)
    return item


def _set_execution_status(execution_id: str, status: str, allowed_from: set[str]) -> dict:
    record = _execution(execution_id)
    if record["status"] not in allowed_from:
        raise HTTPException(status_code=409, detail=f"cannot_{status}_from_{record['status']}")
    record["status"] = status
    if status == "finished":
        runtime = record.get("runtime_log") or {}
        runtime["progress_percent"] = 100
        record["runtime_log"], record["finished_at"] = runtime, utc_now_iso()
    saved = _present_execution(_repository().update_execution(record))
    if status == "finished":
        saved["next_required_action"] = "submit_final_inspection"
    return saved


@router.post("/formal-process/executions/{execution_id}/pause")
def pause(execution_id: str) -> dict: return _set_execution_status(execution_id, "paused", {"running"})


@router.post("/formal-process/executions/{execution_id}/resume")
def resume(execution_id: str) -> dict: return _set_execution_status(execution_id, "running", {"paused"})


@router.post("/formal-process/executions/{execution_id}/abort")
def abort(execution_id: str) -> dict: return _set_execution_status(execution_id, "aborted", {"running", "paused"})


@router.post("/formal-process/executions/{execution_id}/finish")
def finish(execution_id: str) -> dict: return _set_execution_status(execution_id, "finished", {"running"})


@router.post("/formal-process/executions/{execution_id}/inspection")
def inspection(execution_id: str, payload: dict) -> dict:
    execution = _execution(execution_id)
    if execution["status"] != "finished":
        raise HTTPException(status_code=409, detail="formal_process_not_finished")
    inspection_id = stable_id("inspection", execution_id, utc_now_iso())
    required = payload.get("required_metrics") or []
    missing = [key for key in required if (payload.get("measurements") or {}).get(key) is None]
    record = {"inspection_id": inspection_id, "execution_id": execution_id,
              "measurement_plan": {"required_metrics": required}, "required_metrics": required,
              "measurements": payload.get("measurements") or {}, "defects": payload.get("defects") or [],
              "files": payload.get("files") or [], "completeness_status": "complete" if not missing else "incomplete",
              "missing": missing, "created_at": utc_now_iso()}
    return _repository().save_inspection(record)


@router.post("/inspection-records/{inspection_id}/evaluate")
def evaluate_inspection(inspection_id: str, payload: dict) -> dict:
    item = _repository().get_inspection(inspection_id)
    if not item:
        raise HTTPException(status_code=404, detail="inspection_not_found")
    required = (item.get("measurement_plan") or {}).get("required_metrics") or []
    result = quality_decision(required, item.get("measurements") or {}, payload.get("constraint_results") or {})
    record = {"quality_decision_id": stable_id("quality", inspection_id, utc_now_iso()),
              "inspection_id": inspection_id, **result, "basis": {"constraint_results": payload.get("constraint_results") or {}},
              "reviewer_comment": payload.get("reviewer_comment"), "created_at": utc_now_iso()}
    return _repository().save_quality_decision(record)


@router.post("/tasks/{task_id}/rework/assess")
def rework_assess(task_id: str, payload: dict) -> dict:
    return {"task_id": task_id, "rework_required": payload.get("quality_decision") == "rework_required",
            "requires_trial_reassessment": True}


@router.post("/tasks/{task_id}/rework/plans")
def rework_plan(task_id: str, payload: dict) -> dict:
    plan_id = stable_id("rework", task_id, utc_now_iso())
    campaign = CampaignService().create(campaign_id=plan_id, task_id=task_id,
        campaign_type="rework_campaign", fidelity_level="rework",
        material_context=payload.get("material_context") or {},
        equipment_revision=payload.get("equipment_revision") or "unknown",
        active_variables=payload.get("active_variables") or [],
        fixed_parameters=payload.get("fixed_parameters") or {},
        objectives=payload.get("objectives") or [{"name": "recover_quality"}],
        hard_constraints=payload.get("hard_constraints") or [],
        soft_constraints=payload.get("soft_constraints") or [],
        search_space=payload.get("search_space") or {}, budget=payload.get("budget") or {"max_iterations": 1})
    _repository().set_campaign_status(plan_id, "approval_pending", utc_now_iso())
    return {"rework_plan_id": plan_id, **campaign.model_dump(mode="json"), "status": "approval_pending"}


@router.post("/rework/plans/{rework_plan_id}/approve")
def approve_rework(rework_plan_id: str) -> dict:
    record = _repository().approve_rework(rework_plan_id, utc_now_iso())
    if not record:
        raise HTTPException(status_code=404, detail="rework_plan_not_found")
    return record


@router.post("/tasks/{task_id}/results/validate")
def validate_result(task_id: str, payload: dict) -> dict:
    required = ["execution_id", "equipment_revision", "material_batch", "parameters", "measurements"]
    missing = [key for key in required if payload.get(key) in (None, "", {})]
    return {"task_id": task_id, "validation_status": "valid" if not missing else "invalid", "missing": missing}


@router.post("/tasks/{task_id}/experiment-records")
def experiment_record(task_id: str, payload: dict) -> dict:
    experiment_id = stable_id("experiment", task_id, str(payload.get("execution_id")))
    record = {"experiment_id": experiment_id, "task_id": task_id, "created_at": utc_now_iso(),
              "bo_eligible": False, **payload}
    return _repository().save_experiment(record)


@router.post("/experiment-records/{experiment_id}/bo-eligibility")
def experiment_eligibility(experiment_id: str) -> dict:
    experiment = _repository().get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    result = bo_sample_eligibility(experiment)
    experiment["bo_eligible"] = result["eligible"]
    _repository().save_experiment(experiment)
    return result


@router.post("/tasks/{task_id}/knowledge-candidates")
def knowledge_candidate(task_id: str, payload: dict) -> dict:
    return {"candidate_id": stable_id("knowledge-candidate", task_id, utc_now_iso()), "task_id": task_id,
            "status": "pending_review", "validated_rule_created": False, **payload}


@router.post("/tasks/{task_id}/reports")
def create_report(task_id: str, payload: dict) -> dict:
    return TaskReportService().generate(task_id, payload, payload.get("run_id"))


@router.post("/tasks/{task_id}/archive")
def archive_task(task_id: str, payload: dict) -> dict:
    allowed, missing = archive_gate(quality_decided=bool(payload.get("quality_decided")),
        report_generated=bool(payload.get("report_generated")),
        experiment_record_validated=bool(payload.get("experiment_record_validated")))
    if not allowed:
        raise HTTPException(status_code=409, detail={"missing": missing})
    return {"task_id": task_id, "status": "completed", "archived_at": utc_now_iso()}
