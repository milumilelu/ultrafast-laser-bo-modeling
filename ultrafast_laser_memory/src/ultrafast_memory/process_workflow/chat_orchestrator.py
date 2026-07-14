from __future__ import annotations

import json
from typing import Any

from ultrafast_agent.task_intake import (
    ClarificationContextService,
    MissingFieldEvaluator,
    update_task_spec_contract,
)
from ultrafast_agent.runtime import ToolExecutor, ToolRegistry
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.chat.workflow_projection import WorkflowProjectionService
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.trial.service import TrialApplicationService
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.workflows.service import TaskWorkflowService
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso

from .closure import archive_gate, bo_sample_eligibility, quality_decision
from .campaign import CampaignService
from .agent_controller import ProcessAgentController
from .business_state import BusinessState, BusinessStateController, allowed_agent_actions
from .events import record_process_event
from .recommendation_service import recommend_trial_parameters
from .repository import ProcessWorkflowRepository
from .tools import parameter_provenance_registry_tool
from .presentation import FIELD_LABELS, FIELD_QUESTIONS, STATUS_LABELS, localize_action, stage_label


TRIAL_CHOICES = {
    "简化试切": "simple_trial_cut", "simple_trial_cut": "simple_trial_cut",
    "完整试切": "full_trial_cut", "full_trial_cut": "full_trial_cut",
    "跳过试切": "skip_trial", "skip_trial": "skip_trial",
}

def process_progress(state: dict[str, Any], next_action: dict[str, Any]) -> dict[str, Any]:
    projection = WorkflowProjectionService.build_process(
        task_spec=state.get("task_spec") or {},
        workflow_state=state,
        next_action=next_action,
    )
    current = projection.substatus
    business_state = BusinessState(projection.business_state)
    overview = [
        {**item, "status": STATUS_LABELS[item["status_code"]]}
        for item in projection.workflow_overview
    ]
    blocked = bool(next_action.get("blocking")) or business_state == BusinessState.BLOCKED
    return {"workflow_overview": overview, "business_state": projection.business_state,
            "substatus": current, "current_stage_code": current, "current_stage": current,
            "current_stage_label": stage_label(current),
            "completed_stage_codes": [item["step_code"] for item in overview if item["status_code"] == "completed"],
            "completed_stages": [item["step"] for item in overview if item["status_code"] == "completed"],
            "pending_stage_codes": [item["step_code"] for item in overview if item["status_code"] == "pending"],
            "pending_stages": [item["step"] for item in overview if item["status_code"] == "pending"],
            "blocked_stage_codes": [current] if blocked else [],
            "blocked_stages": [stage_label(current)] if blocked else [],
            "next_required_action": localize_action(next_action),
            "completed_steps": len(projection.completed_steps),
            "total_steps": len(projection.workflow_overview),
            "percent": projection.progress_percent}


def run_process_chat_turn(session_id: str, message: str, message_id: str | None = None) -> dict[str, Any]:
    state = get_session_state(session_id)
    collected = dict(state.get("collected_slots") or {})
    task = dict(collected.get("process_task_spec") or {})
    workflow = dict(collected.get("process_workflow") or {})
    BusinessStateController.ensure(workflow)
    context = ClarificationContextService.build(state, "complex_process_task", task)
    allowed_actions = allowed_agent_actions(workflow["business_state"])
    workflow["allowed_actions"] = allowed_actions
    if _task_intake_required(workflow, task, context):
        action = ProcessAgentController(create_llm_client(get_llm_config())).decide(
            message=message,
            task_spec=task,
            business_state=workflow["business_state"],
            context=context,
            allowed_actions=allowed_actions,
            campaign=workflow.get("campaign"),
            recent_tool_results=collected.get("process_agent_tool_history") or [],
        )
        agent_events = [_record_agent_decision(session_id, message_id, action, workflow)]
        tool_output: dict[str, Any] | None = None
        if action.action == "call_tool" and action.tool_name == "update_task_spec":
            agent_events.append(_record_agent_tool_call(
                session_id, message_id, action, workflow.get("substatus") or "INTAKE"
            ))
            registry = ToolRegistry()
            registry.register(update_task_spec_contract())
            execution = ToolExecutor(registry).execute(
                "update_task_spec",
                action.arguments,
                {
                    "session_id": session_id,
                    "message_id": message_id,
                    "user_message": message,
                    "clarification_context": context.model_dump(mode="json"),
                },
            )
            if execution.status == "succeeded" and isinstance(execution.output, dict):
                tool_output = execution.output
            else:
                tool_output = {
                    "status": "failed",
                    "error_code": execution.error_code,
                    "message": execution.error_message,
                    "applied": [],
                    "rejected": [],
                    "conflicts": [],
                    "remaining_missing": list(context.pending_fields),
                }
            agent_events.append(_record_agent_tool_result(
                session_id, message_id, tool_output, workflow.get("substatus") or "INTAKE"
            ))
            if tool_output.get("task_spec") is not None:
                task = dict(tool_output["task_spec"])
                collected["process_task_spec"] = task
                collected["process_task_field_provenance"] = tool_output.get("field_provenance") or {}
                collected["process_task_revision_history"] = tool_output.get("revision_history") or []
            missing = list(tool_output.get("remaining_missing") or [])
        else:
            missing = MissingFieldEvaluator.evaluate(task, context)
        history_entry = {
            "message_id": message_id,
            "action": action.model_dump(mode="json"),
            "tool_result": tool_output,
        }
        collected["process_agent_tool_history"] = [
            *(collected.get("process_agent_tool_history") or [])[-19:], history_entry,
        ]
    else:
        missing = []
        action = None
        tool_output = None
        agent_events = []
    if missing:
        clarification_round = min(int(workflow.get("clarification_round") or 0) + 1, 3)
        previous_questions = [
            *(workflow.get("previous_questions") or [])[-20:],
            *[
                {
                    "clarification_round": clarification_round,
                    "field": field,
                    "question": FIELD_QUESTIONS.get(field, field),
                }
                for field in missing
            ],
        ]
        BusinessStateController.transition(workflow, "REQUIREMENTS_PENDING")
        workflow.update({"missing_fields": missing,
                         "clarification_round": clarification_round,
                         "max_clarification_rounds": 3,
                         "ordered_fields": missing,
                         "previous_questions": previous_questions,
                         "allowed_actions": allowed_agent_actions(BusinessState.INTAKE),
                         "agent_action": action.model_dump(mode="json") if action else None,
                         "last_tool_result": tool_output,
                         "task_spec": task,
                         "field_provenance": collected.get("process_task_field_provenance") or {},
                         "revision_history": collected.get("process_task_revision_history") or []})
        collected["process_workflow"] = workflow
        update_session_state(session_id, {"collected_slots": collected,
            "active_workflow": "complex_process_task", "active_skill": "complex_process_task",
            "workflow_stage": "clarification", "pending_questions": missing})
        return {
            "content": (
                (action.message + "\n\n" + _requirements_message(task, missing, clarification_round))
                if action and action.action == "ask_user" and action.message
                else action.message if action and action.action == "direct_answer" and action.message
                else _tool_failure_message(tool_output, missing) if tool_output and tool_output.get("status") == "failed"
                else _requirements_message(task, missing, clarification_round)
            ),
            "state": workflow,
            "next_action": {
                "action_type": "submit_required_fields",
                "required_fields": missing,
                "blocking": True,
            },
            "events": agent_events,
        }

    workflow.update({
        "missing_fields": [],
        "task_spec": task,
        "field_provenance": collected.get("process_task_field_provenance") or {},
        "revision_history": collected.get("process_task_revision_history") or [],
        "agent_action": action.model_dump(mode="json") if action else workflow.get("agent_action"),
        "last_tool_result": tool_output,
    })

    selected = _trial_choice(message) or workflow.get("selected_trial_mode")
    if not selected:
        result = _execute_workflow(session_id, task, selected_trial_mode=None)
        selection = result["data"].get("trial_selection") or {}
        BusinessStateController.transition(workflow, "TRIAL_MODE_PENDING")
        workflow["workflow_run_id"] = result["run_id"]
        collected["process_workflow"] = workflow
        update_session_state(session_id, {"collected_slots": collected, "workflow_stage": "trial_mode_pending",
                                          "pending_questions": ["trial_mode"]})
        return {"content": _trial_choice_message(selection), "state": workflow,
                "next_action": selection.get("next_required_action") or {"action_type": "select_trial_mode",
                    "allowed_values": list(TRIAL_CHOICES.values()), "blocking": True},
                "events": [*agent_events, *result["events"]],
                "workflow_result": result}

    if BusinessState(workflow["business_state"]) in {
        BusinessState.READY_FOR_EXTERNAL_PROCESS,
        BusinessState.WAITING_EXTERNAL_RESULT,
        BusinessState.QUALITY_REVIEW,
    } and workflow.get("execution_step") in {
        "FORMAL_PROCESS_READY", "FORMAL_PREFLIGHT", "FORMAL_PROCESS_RUNNING",
        "FINAL_INSPECTION_PENDING", "QUALITY_DECISION", "REPORT_PENDING", "ARCHIVE_PENDING",
    }:
        formal_result = _run_formal_turn(session_id, message, collected, workflow, task)
        formal_result["events"] = [*agent_events, *(formal_result.get("events") or [])]
        return formal_result

    if not workflow.get("trial_plan"):
        allow_exploration = any(marker in message for marker in ("允许探索性候选", "同意探索性候选", "允许LLM兜底"))
        recommendation, call_order = recommend_trial_parameters(
            {"task_id": f"process-{session_id}", **task}, build_machine_bounds(),
            allow_llm_fallback=allow_exploration)
        workflow["parameter_tool_chain"] = call_order
        workflow["parameter_recommendation"] = recommendation.model_dump(mode="json")
        if not recommendation.parameters:
            workflow["selected_trial_mode"] = selected
            BusinessStateController.transition(
                workflow,
                "BLOCKED" if allow_exploration else "PARAMETER_SOURCE_APPROVAL_PENDING",
            )
            collected["process_workflow"] = workflow
            update_session_state(session_id, {"collected_slots": collected,
                "workflow_stage": workflow["substatus"].lower(),
                "pending_questions": [] if allow_exploration else ["allow_exploratory_candidates"]})
            content = ("参数工具链已依次执行：" + " → ".join(call_order) + "。\n"
                       "BO 与 RAG 均不足。" +
                       ("受控 LLM 参数工具也未生成通过校验的候选，流程已阻塞。" if allow_exploration else
                        "如需继续简化试切，请明确回复“允许探索性候选”；该候选仅能用于简化试切。"))
            return {"content": content, "state": workflow,
                    "next_action": {"action_type": "resolve_parameter_evidence" if allow_exploration else "approve_llm_fallback",
                                    "allowed_values": ["允许探索性候选"] if not allow_exploration else [], "blocking": True},
                    "events": agent_events}
        candidate = {item.name: item.value for item in recommendation.parameters if item.value is not None}
        provenance = parameter_provenance_registry_tool(recommendation)
        result = _execute_workflow(session_id, task, selected_trial_mode=selected,
                                   approved_parameter_candidates=[candidate])
        plan = result["data"].get("trial_plan")
        if not plan:
            blocked = BusinessStateController.transition({}, "BLOCKED")
            return {"content": "试切模式不允许或试切方案生成失败，流程已阻塞。", "state": blocked,
                    "next_action": {"action_type": "review_trial_mode", "blocking": True},
                    "events": [*agent_events, *result["events"]]}
        BusinessStateController.transition(workflow, "TRIAL_RESULT_PENDING")
        workflow.update({"selected_trial_mode": selected,
                         "trial_plan": plan, "parameter_provenance": provenance,
                         "workflow_run_id": result["run_id"]})
        workflow["campaign"] = _create_campaign(session_id, task, selected, candidate).model_dump(mode="json")
        collected["process_workflow"] = workflow
        update_session_state(session_id, {"collected_slots": collected, "workflow_stage": "trial_result_pending",
                                          "pending_questions": ["trial_result"]})
        return {"content": _trial_plan_message(plan), "state": workflow,
                "next_action": _trial_result_contract(), "events": [*agent_events, *result["events"]],
                "workflow_result": result}

    payload = _json_payload(message)
    if payload is None:
        return {"content": "当前等待试切结果。请按下方 JSON 输入契约提交，不得以文字确认代替实测数据。",
                "state": workflow, "next_action": _trial_result_contract(), "events": agent_events}
    evaluation = _ingest_and_evaluate(workflow["trial_plan"], payload)
    BusinessStateController.transition(workflow, "TRIAL_RESULT_EVALUATION")
    workflow.update({"trial_evaluation": evaluation,
                     "verified_trial_payload": payload})
    collected["process_workflow"] = workflow
    update_session_state(session_id, {"collected_slots": collected, "workflow_stage": "trial_result_evaluation",
                                      "pending_questions": []})
    decision = ((evaluation.get("evaluation") or {}).get("decision") or "unknown")
    if decision == "pass":
        campaign_data = workflow.get("campaign")
        if campaign_data:
            campaign_service = CampaignService()
            campaign_service.load(campaign_data["campaign_id"])
            observation = campaign_service.ingest_observation(campaign_data["campaign_id"], {
                "candidate_id": stable_id("candidate", stable_id("iteration", campaign_data["campaign_id"], "0"), "0"),
                "parameters": payload["actual_parameters"], "units": payload["parameter_units"],
                "equipment_revision": payload["equipment_revision"], "material_batch": payload["material_batch"],
                "measurements": payload["measurements"], "quality_metrics": payload["measurements"],
                "constraint_results": {"trial_acceptance": True}, "attachments": payload["files"]})
            workflow["campaign_observation"] = observation
            workflow["model_snapshot"] = campaign_service.update_model(campaign_data["campaign_id"])
        BusinessStateController.transition(workflow, "FORMAL_PROCESS_READY")
        collected["process_workflow"] = workflow
        update_session_state(session_id, {"collected_slots": collected, "workflow_stage": "formal_process_ready",
                                          "pending_questions": ["formal_preflight"]})
        content = ("试切结果已通过。正式参数仅采用本次已验证的 actual_parameters；"
                   "探索性候选不具备正式加工权限。请提交 preflight JSON。")
        next_action = {"action_type": "submit_formal_preflight", "blocking": True,
                       "required_fields": ["equipment_revision", "material_batch", "operator_confirmation"]}
    else:
        content = f"试切结果已完成结构化评价：{decision}。流程不能进入正式加工。"
        next_action = {"action_type": "review_trial_failure", "blocking": True}
    return {"content": content, "state": workflow, "next_action": next_action, "events": agent_events}


def _run_formal_turn(session_id: str, message: str, collected: dict[str, Any], workflow: dict[str, Any],
                     task: dict[str, Any]) -> dict[str, Any]:
    payload = _json_payload(message)
    repository = ProcessWorkflowRepository()
    state = workflow["execution_step"]
    if state == "FORMAL_PROCESS_READY":
        required = ("equipment_revision", "material_batch", "operator_confirmation")
        missing = [key for key in required if not payload or payload.get(key) in (None, "", False)]
        trial = workflow["verified_trial_payload"]
        if payload and payload.get("equipment_revision") != trial.get("equipment_revision"):
            missing.append("equipment_revision_match")
        if missing:
            pending = dict(workflow)
            BusinessStateController.transition(pending, "FORMAL_PREFLIGHT")
            return _save_formal(session_id, collected, pending,
                "正式加工 preflight 未通过：" + "、".join(sorted(set(missing))) + "。",
                {"action_type": "submit_formal_preflight", "required_fields": list(required), "blocking": True})
        plan_id = stable_id("formal-plan", f"process-{session_id}", workflow["trial_plan"]["trial_plan_id"])
        plan = repository.save_plan({"plan_id": plan_id, "task_id": f"process-{session_id}",
            "trial_result_id": (workflow.get("trial_evaluation") or {}).get("result_id"),
            "parameter_recommendation_id": (workflow.get("parameter_recommendation") or {}).get("recommendation_id"),
            "equipment_revision": payload["equipment_revision"], "approved_window": trial["actual_parameters"],
            "toolpath": trial.get("actual_path") or {}, "monitoring_plan": {"checkpoints": [10, 25, 50, 75, 100]},
            "stop_conditions": ["delamination", "thermal_damage", "equipment_alarm"],
            "release_status": "preflight_passed", "created_at": utc_now_iso()})
        execution_id = stable_id("formal-exec", plan_id, utc_now_iso())
        execution = {"execution_id": execution_id, "plan_id": plan_id,
            "actual_parameters": trial["actual_parameters"], "actual_path": trial.get("actual_path") or {},
            "runtime_log": {"progress_percent": 0, "checkpoints": [], "source": "user_reported"},
            "started_at": utc_now_iso(), "finished_at": None, "status": "external_in_progress"}
        repository.save_execution(execution)
        BusinessStateController.transition(workflow, "FORMAL_PROCESS_RUNNING")
        workflow.update({"formal_plan": plan,
                         "formal_execution": execution, "material_batch": payload["material_batch"]})
        workflow["formal_campaign"] = _create_campaign(
            session_id, task, "formal_process", trial["actual_parameters"], payload["equipment_revision"]
        ).model_dump(mode="json")
        return _save_formal(session_id, collected, workflow,
            "Preflight 已通过，已登记用户的外部正式加工开始。系统未连接、控制或监控设备；请由用户提交检查点 JSON。",
            {"action_type": "submit_formal_checkpoint", "required_fields": ["progress_percent", "deviation_level", "observation"], "blocking": True})
    if state == "FORMAL_PREFLIGHT":
        BusinessStateController.transition(workflow, "FORMAL_PROCESS_READY")
        return _run_formal_turn(session_id, message, collected, workflow, task)
    if state == "FORMAL_PROCESS_RUNNING":
        if not payload or "progress_percent" not in payload:
            return _save_formal(session_id, collected, workflow, "等待正式加工检查点 JSON。",
                {"action_type": "submit_formal_checkpoint", "required_fields": ["progress_percent", "deviation_level"], "blocking": True})
        execution = repository.get_execution(workflow["formal_execution"]["execution_id"])
        progress = float(payload["progress_percent"])
        current = float((execution.get("runtime_log") or {}).get("progress_percent", 0))
        if not current <= progress <= 100:
            return _save_formal(session_id, collected, workflow, "检查点进度必须单调且位于 0–100%。",
                {"action_type": "correct_formal_checkpoint", "blocking": True})
        level = int(payload.get("deviation_level", 0))
        decision = "abort_return_to_trial" if level >= 3 else "pause_for_confirmation" if level == 2 else "continue"
        checkpoint = {"checkpoint_id": stable_id("checkpoint", execution["execution_id"], str(progress)),
            "execution_id": execution["execution_id"], "checkpoint_type": "user_reported_external_progress",
            "progress_percent": progress, "observation": payload.get("observation") or {},
            "decision": decision, "created_at": utc_now_iso()}
        repository.save_checkpoint(checkpoint)
        runtime = execution.get("runtime_log") or {}
        runtime["progress_percent"] = progress
        runtime.setdefault("checkpoints", []).append(checkpoint)
        execution["runtime_log"] = runtime
        if level >= 3:
            execution["status"] = "aborted"
            BusinessStateController.transition(workflow, "BLOCKED")
            repository.update_execution(execution)
            return _save_formal(session_id, collected, workflow, "发现 Level 3 偏差，已中止并返回试切评估。",
                {"action_type": "return_to_trial", "blocking": True})
        if level == 2:
            execution["status"] = "paused"
            repository.update_execution(execution)
            return _save_formal(session_id, collected, workflow, "Level 2 偏差，已暂停等待人工确认。",
                {"action_type": "confirm_checkpoint_resume", "blocking": True})
        if progress == 100:
            execution["status"], execution["finished_at"] = "finished", utc_now_iso()
            BusinessStateController.transition(workflow, "FINAL_INSPECTION_PENDING")
            repository.update_execution(execution)
            return _save_formal(session_id, collected, workflow, "正式加工完成，但任务尚不能关闭；请提交最终检测 JSON。",
                {"action_type": "submit_final_inspection", "required_fields": ["required_metrics", "measurements", "constraint_results", "files"], "blocking": True})
        repository.update_execution(execution)
        return _save_formal(session_id, collected, workflow, f"检查点 {progress:g}% 已记录，决策：continue。",
            {"action_type": "submit_formal_checkpoint", "required_fields": ["progress_percent", "deviation_level"], "blocking": True})
    if state == "FINAL_INSPECTION_PENDING":
        required = ["required_metrics", "measurements", "constraint_results", "files"]
        missing = [key for key in required if not payload or payload.get(key) in (None, "", [], {})]
        if missing:
            return _save_formal(session_id, collected, workflow, "最终检测数据不完整，质量状态为 QUALITY_INCONCLUSIVE。",
                {"action_type": "complete_final_inspection", "required_fields": missing, "blocking": True})
        decision = quality_decision(payload["required_metrics"], payload["measurements"], payload["constraint_results"])
        if decision["decision"] != "accepted":
            BusinessStateController.transition(workflow, "QUALITY_DECISION")
            workflow["quality_decision"] = decision
            return _save_formal(session_id, collected, workflow, f"质量判定：{decision['decision']}，不能归档。",
                {"action_type": "assess_rework", "blocking": True})
        execution_id = workflow["formal_execution"]["execution_id"]
        experiment = {"task_id": f"process-{session_id}", "execution_id": execution_id,
            "equipment_revision": workflow["verified_trial_payload"]["equipment_revision"],
            "material_batch": workflow["material_batch"],
            "parameters": workflow["verified_trial_payload"]["actual_parameters"],
            "measurements": payload["measurements"], "quality_decision": "accepted",
            "fidelity_level": "formal_process", "validation_status": "valid"}
        eligibility = bo_sample_eligibility(experiment)
        experiment.update({"experiment_id": stable_id("experiment", f"process-{session_id}", execution_id),
                           "bo_eligible": eligibility["eligible"], "created_at": utc_now_iso()})
        repository.save_experiment(experiment)
        report = TaskReportService().generate(f"process-{session_id}", {
            "task_spec": task, "trial_plan": workflow.get("trial_plan"),
            "trial_result": workflow.get("trial_evaluation"), "quality_plan": {"decision": decision},
            "bo": {"model_status": eligibility["status"]}, "next_step": "archived",
            "business_state": BusinessState.COMPLETED.value, "substatus": "COMPLETED"})
        allowed, _ = archive_gate(quality_decided=True, report_generated=report["status"] == "completed",
                                  experiment_record_validated=True)
        BusinessStateController.transition(workflow, "COMPLETED" if allowed else "ARCHIVE_PENDING")
        workflow.update({"quality_decision": decision,
                         "experiment_record": experiment, "bo_eligibility": eligibility,
                         "report": report})
        return _save_formal(session_id, collected, workflow,
            "最终检测通过；实验记录、BO 准入判定和任务报告已生成，任务已归档关闭。",
            {"action_type": "none", "blocking": False})
    return _save_formal(session_id, collected, workflow, "当前正式加工状态需要人工审查。",
                          {"action_type": "review_workflow_state", "blocking": True})


def _save_formal(session_id: str, collected: dict[str, Any], workflow: dict[str, Any],
                 content: str, action: dict[str, Any]) -> dict[str, Any]:
    if not workflow.get("business_state"):
        BusinessStateController.ensure(workflow, str(workflow.get("state") or "BLOCKED"))
    collected["process_workflow"] = workflow
    update_session_state(session_id, {"collected_slots": collected, "workflow_stage": workflow["execution_step"].lower(),
                                      "pending_questions": [] if not action.get("blocking") else [action["action_type"]]})
    return {"content": content, "state": workflow, "next_action": action, "events": []}


def _create_campaign(session_id: str, task: dict[str, Any], mode: str,
                     parameters: dict[str, Any], equipment_revision: str | None = None):
    formal = mode == "formal_process"
    fidelity = "formal_process" if formal else "full_trial" if mode == "full_trial_cut" else "simple_trial"
    campaign_type = "formal_process_campaign" if formal else \
        "full_trial_campaign" if fidelity == "full_trial" else "simple_trial_campaign"
    equipment = build_machine_bounds()
    service = CampaignService()
    campaign = service.create(
        campaign_id=stable_id("campaign", session_id, fidelity), task_id=f"process-{session_id}",
        campaign_type=campaign_type, fidelity_level=fidelity,
        material_context={"material": task.get("material"), "thickness_mm": task.get("thickness_mm")},
        equipment_revision=equipment_revision or equipment.get("revision_id") or "unknown",
        active_variables=list(parameters), fixed_parameters={},
        objectives=[{"name": "quality_compliance"}],
        hard_constraints=[{"name": task.get("quality_requirement") or "task_quality_requirement"}],
        soft_constraints=[] if task.get("efficiency_requirement") == "none" else [{"name": "efficiency"}],
        search_space={key: (equipment.get("machine_bounds") or {}).get(key, [value, value])
                      for key, value in parameters.items()},
        budget={"max_iterations": 1 if formal else 3, "max_batch_size": 1 if formal else 9},
    )
    service.create_iteration(campaign.campaign_id, {"effective_sample_count": 0,
        "model_mode": "rule_based_cold_start", "fidelity_level": fidelity}, [parameters])
    return campaign


def _execute_workflow(session_id: str, task: dict[str, Any], selected_trial_mode: str | None,
                      approved_parameter_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task_spec = {"component_type": task.get("component_type") or "workpiece", **task}
    return TaskWorkflowService().execute("complex_process_task", {
        "task_id": f"process-{session_id}", "session_id": session_id, "task_spec": task_spec,
        "question": " ".join(str(value) for value in task.values()),
        "selected_trial_mode": selected_trial_mode, "display_mode": "debug",
        "approved_parameter_candidates": approved_parameter_candidates or [],
    })


def _trial_choice(message: str) -> str | None:
    text = message.strip().lower()
    for marker, value in TRIAL_CHOICES.items():
        if marker.lower() in text:
            return value
    return None


def _json_payload(message: str) -> dict[str, Any] | None:
    text = message.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:].lstrip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _ingest_and_evaluate(plan: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required = ("equipment_revision", "material_batch", "actual_parameters", "parameter_units",
                "actual_path", "measurements", "defects", "files")
    missing = [key for key in required if key not in payload]
    if missing:
        return {"evaluation": {"decision": "inconclusive"}, "missing_fields": missing}
    service = TrialApplicationService()
    execution = service.start_execution(plan["trial_plan_id"], {
        "equipment_revision": payload["equipment_revision"], "actual_parameters": payload["actual_parameters"],
        "actual_path": payload["actual_path"], "monitoring_summary": payload.get("monitoring_summary") or {}})
    result = service.create_result(execution["execution_id"], {
        "measurements": payload["measurements"], "defects": payload["defects"]})
    return service.evaluate(result["result_id"], {
        "reviewer_comment": payload.get("reviewer_comment"),
        "confirm_conditional": bool(payload.get("confirm_conditional"))})


def _task_intake_required(workflow: dict[str, Any], task: dict[str, Any], context) -> bool:
    business_state = workflow.get("business_state")
    if business_state in {None, "", BusinessState.INTAKE.value}:
        return True
    return bool(MissingFieldEvaluator.evaluate(task, context))


def _record_agent_decision(
    session_id: str,
    message_id: str | None,
    action,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    selected = action.tool_name if action.action == "call_tool" else action.action
    return record_process_event(
        session_id=session_id,
        message_id=message_id,
        event_type="agent_decision",
        stage=workflow.get("substatus") or "INTAKE",
        title="Agent 行动决策",
        summary=action.decision_summary,
        skill="complex_process_task",
        tool="main_agent",
        payload={
            "action": action.action,
            "selected": selected,
            "provider": action.provider,
            "model": action.model,
            "allowed_actions": workflow.get("allowed_actions") or [],
        },
        status="completed",
    )


def _record_agent_tool_call(
    session_id: str,
    message_id: str | None,
    action,
    stage: str,
) -> dict[str, Any]:
    updates = list(action.arguments.get("updates") or [])
    return record_process_event(
        session_id=session_id,
        message_id=message_id,
        event_type="tool_started",
        stage=stage,
        title="调用 update_task_spec",
        summary=f"主 Agent 请求校验并提交 {len(updates)} 个结构化任务字段。",
        skill="complex_process_task",
        tool="update_task_spec",
        payload={"fields": [str(item.get("field_name")) for item in updates]},
        status="running",
    )


def _record_agent_tool_result(
    session_id: str,
    message_id: str | None,
    result: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    status = str(result.get("status") or "failed")
    applied = list(result.get("applied") or [])
    missing = list(result.get("remaining_missing") or [])
    return record_process_event(
        session_id=session_id,
        message_id=message_id,
        event_type="tool_completed" if status != "failed" else "tool_failed",
        stage=stage,
        title="update_task_spec 执行结果",
        summary=(
            "已写入：" + ("、".join(applied) or "无") + "；"
            "剩余缺失：" + ("、".join(missing) or "无") + "。"
        ),
        skill="complex_process_task",
        tool="update_task_spec",
        payload={
            "status": status,
            "applied": applied,
            "rejected": result.get("rejected") or [],
            "conflicts": result.get("conflicts") or [],
            "remaining_missing": missing,
            "error_code": result.get("error_code"),
        },
        status="completed" if status == "success" else "warning" if status == "partial" else "failed",
    )


def _tool_failure_message(result: dict[str, Any], missing: list[str]) -> str:
    reason = result.get("error_code") or result.get("message") or "tool_failed"
    labels = "、".join(FIELD_LABELS.get(field, field) for field in missing)
    return f"任务状态写入工具未成功（{reason}）。现有状态未被覆盖。仍缺少：{labels}。"


def _requirements_message(task: dict[str, Any], missing: list[str], clarification_round: int = 1) -> str:
    questions = "\n".join(f"{index}. {FIELD_QUESTIONS.get(field, '请补充' + FIELD_LABELS.get(field, field) + '。')}"
                          for index, field in enumerate(missing, start=1))
    labels = "、".join(FIELD_LABELS.get(field, field) for field in missing)
    limit = "\n\n已完成 3 轮澄清；若仍无法补齐，系统只提供保守方案，不能进入确定性 BO 参数推荐。" if clarification_round >= 3 else ""
    return ("加工任务进入需求确认阶段，工作流已停在“等待补充加工要求”阶段。\n\n"
            f"还缺少：{labels}\n\n请回答：\n{questions}\n\n"
            "字段完整前不会读取工艺参数证据、生成参数或运行贝叶斯优化。" + limit)


def _trial_choice_message(selection: dict[str, Any]) -> str:
    return ("任务需求、设备、RAG、证据评价和试切必要性评估已执行。\n\n"
            f"当前阶段：等待选择试切方式\n系统建议：{selection.get('recommended_mode')}\n"
            "请选择：[简化试切] [完整试切] [跳过试切]。系统不会替您默认选择。")


def _trial_plan_message(plan: dict[str, Any]) -> str:
    return (f"已生成 {plan.get('trial_mode')} 方案（{plan.get('trial_plan_id')}）。\n"
            "当前阶段：等待提交试切结果。尚未收到结果，不会声称试切通过或进入贝叶斯优化。")


def _trial_result_contract() -> dict[str, Any]:
    return {"action_type": "submit_trial_result", "blocking": True,
            "required_fields": ["equipment_revision", "material_batch", "actual_parameters", "parameter_units",
                                "actual_path", "measurements", "defects", "files"],
            "attachments": ["cut_edge_photo", "measurement_file"]}
