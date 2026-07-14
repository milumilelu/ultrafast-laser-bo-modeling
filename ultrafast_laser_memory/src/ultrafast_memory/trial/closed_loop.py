from __future__ import annotations

from typing import Any
import uuid

from ultrafast_agent.process_recommendations.service import (
    BOTrainingApprovalService,
    ProcessRecommendationService,
)
from ultrafast_agent.runtime.event_service import canonical_agent_events
from ultrafast_domain.trial.campaign import (
    TRIAL_STRATEGY_POLICIES,
    TrialCampaign,
    TrialDecision,
    TrialIteration,
    TrialObservation,
    TrialStrategy,
)
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_integrations.storage.trial_campaign_repository import TrialCampaignRepository
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.process_workflow.business_state import (
    BusinessState,
    BusinessStateController,
)
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.trial.decision import TrialDecisionService


SOURCE_ORDER = (
    ("bo", "bo_parameter_recommendation"),
    ("approved_prior", "approved_prior_or_rule"),
    ("rag", "rag_parameter_recommendation"),
    ("llm_fallback", "llm_trial_fallback"),
)


class TrialClosedLoopService:
    """Application service connecting existing recommendation, CAM, BO, and event boundaries."""

    def __init__(
        self,
        repository: TrialCampaignRepository | None = None,
        recommendations: ProcessRecommendationService | None = None,
        approvals: BOTrainingApprovalService | None = None,
    ):
        self.repository = repository or TrialCampaignRepository()
        self.recommendations = recommendations or ProcessRecommendationService()
        self.approvals = approvals or BOTrainingApprovalService()

    def create_campaign(
        self,
        *,
        task_id: str,
        workflow_id: str,
        task_spec: dict[str, Any],
        search_space: dict[str, Any],
        current_recipe: dict[str, Any],
        parameter_units: dict[str, str],
        equipment_revision: str,
        targets: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not task_spec.get("material") or not task_spec.get("process_type"):
            raise ValueError("canonical TaskSpec material and process_type are required")
        campaign = TrialCampaign(
            campaign_id=f"trial_campaign_{uuid.uuid4().hex}",
            task_id=task_id,
            workflow_id=workflow_id,
            task_spec=dict(task_spec),
            search_space=dict(search_space),
            current_recipe=dict(current_recipe),
            parameter_units=dict(parameter_units),
            equipment_revision=equipment_revision,
            targets=dict(targets),
            constraints=dict(constraints or {}),
            metadata={"session_id": session_id, "dataset_sample_ids": []},
        )
        self.repository.save_campaign(campaign)
        event = self._emit(
            campaign,
            "trial_strategy_offered",
            "已提供 conservative、balanced、exploratory 三种试切策略；尚未生成参数。",
            {"strategies": {key.value: value for key, value in TRIAL_STRATEGY_POLICIES.items()}},
            "strategy-offered",
        )
        return {"campaign": campaign.to_dict(), "strategies": event["payload"]["strategies"]}

    def select_strategy(
        self,
        campaign_id: str,
        strategy: str,
        recommendation_options: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        selected = TrialStrategy(strategy)
        result, source = self._select_parameter_source(recommendation_options)
        campaign.strategy = selected.value
        campaign.iteration_budget = int(TRIAL_STRATEGY_POLICIES[selected]["iteration_budget"])
        campaign.substatus = "TRIAL_RECOMMENDATION_PENDING"
        self._emit(
            campaign,
            "trial_strategy_selected",
            f"用户选择试切策略 {selected.value}。",
            {"strategy": selected.value, "policy": TRIAL_STRATEGY_POLICIES[selected]},
            f"strategy-selected:{selected.value}",
        )
        recommendation = self.recommendations.create(
            task_id=campaign.task_id,
            workflow_id=campaign.workflow_id,
            task_spec=campaign.task_spec,
            bo_result=result,
            search_space=campaign.search_space,
            current_recipe=campaign.current_recipe,
            stage="trial_cut",
            parameter_units=campaign.parameter_units,
            parameter_sources={name: source for name in result.get("recommended_parameters") or {}},
            recommendation_source=source,
            source_run_id=result.get("source_run_id") or result.get("bo_run_id"),
        )
        iteration = TrialIteration(
            iteration_id=f"trial_iteration_{uuid.uuid4().hex}",
            campaign_id=campaign.campaign_id,
            iteration_number=1,
            recommendation_id=recommendation.recommendation_id,
            parent_recommendation_id=None,
            created_at=utc_now_iso(),
        )
        self.repository.save_iteration(iteration)
        campaign.current_iteration = 1
        campaign.current_recipe = dict(recommendation.complete_recipe)
        campaign.substatus = "TRIAL_RESULT_PENDING"
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "recommendation_created",
            "已创建 iteration 1 完整试切 Recipe。",
            self._recommendation_event_payload(recommendation.to_dict()),
            f"recommendation:{recommendation.recommendation_id}",
        )
        cam = self.recommendations.cam_parameters(recommendation.recommendation_id)
        self._emit(
            campaign,
            "cam_export_created",
            "已生成仅含字段映射与单位转换的试切 CAM 导出；系统未控制设备。",
            {"recommendation_id": recommendation.recommendation_id},
            f"cam:{recommendation.recommendation_id}",
        )
        return {
            "campaign": campaign.to_dict(),
            "iteration": iteration.to_dict(),
            "recommendation": recommendation.to_dict(),
            "cam_export": cam,
        }

    def submit_feedback(
        self,
        campaign_id: str,
        recommendation_id: str,
        feedback: dict[str, Any],
    ) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        iteration = self.repository.get_iteration_for_recommendation(recommendation_id)
        recommendation = self.recommendations.get(recommendation_id)
        self._validate_feedback(campaign, recommendation, feedback)
        payload = {
            **feedback,
            "run_status": feedback.get("run_status", "completed"),
            "out_of_bounds": self._actual_out_of_bounds(
                feedback["machine_actual_parameters"],
                recommendation["complete_recipe"],
                campaign.search_space,
            ),
        }
        self._emit(
            campaign,
            "trial_feedback_received",
            "已接收用户上报的 CAM 设置、机器实际参数和测量结果。",
            {"recommendation_id": recommendation_id, "run_id": payload.get("run_id")},
            f"feedback:{iteration['iteration_id']}",
        )
        feedback_result = self.recommendations.submit_feedback(recommendation_id, payload)
        eligibility = feedback_result["eligibility"]
        observation = TrialObservation(
            observation_id=f"trial_observation_{uuid.uuid4().hex}",
            campaign_id=campaign_id,
            iteration_id=iteration["iteration_id"],
            recommendation_id=recommendation_id,
            recommended_parameters=dict(recommendation["complete_recipe"]),
            cam_applied_parameters=dict(feedback["cam_applied_parameters"]),
            machine_actual_parameters=dict(feedback["machine_actual_parameters"]),
            measurements=dict(feedback["measurements"]),
            parameter_units=dict(feedback["parameter_units"]),
            measurement_units=dict(feedback["measurement_units"]),
            constraint_results=dict(feedback.get("constraint_results") or {}),
            alarms=tuple(feedback.get("alarms") or ()),
            risk_state=str(feedback.get("risk_state") or "normal"),
            eligibility_report=dict(eligibility),
            created_at=utc_now_iso(),
        )
        self.repository.save_observation(
            observation,
            candidate_id=feedback_result["candidate_id"],
        )
        campaign.substatus = (
            "BO_ELIGIBILITY_APPROVAL_PENDING" if eligibility["eligible"]
            else "TRIAL_FEEDBACK_REJECTED"
        )
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "bo_eligibility_evaluated",
            "试切反馈已完成 BO Eligibility 检查。",
            {"eligible": eligibility["eligible"], "blocking_reasons": eligibility["blocking_reasons"]},
            f"eligibility:{observation.observation_id}",
        )
        return {
            "observation": observation.to_dict(),
            "candidate_id": feedback_result["candidate_id"],
            "eligibility": eligibility,
            "training_sample_created": False,
        }

    def approve_feedback_and_advance(
        self,
        campaign_id: str,
        observation_id: str,
        *,
        approved_by: str,
        next_bo_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        record = self.repository.get_observation(observation_id)
        if not record["eligibility"].get("eligible"):
            raise ValueError("ineligible TrialObservation cannot enter a BO dataset")
        approval = self.approvals.approve(
            record["candidate_id"],
            approved_by,
            list(campaign.metadata.get("dataset_sample_ids") or []),
        )
        dataset = approval["dataset_version"]
        campaign.metadata["dataset_sample_ids"] = list(dataset["sample_ids"])
        campaign.metadata["dataset_version"] = dataset["dataset_version_id"]
        observation = record["observation"]
        decision = TrialDecisionService.decide(
            measurements=observation["measurements"],
            targets=campaign.targets,
            constraints=observation["constraint_results"],
            iteration_number=campaign.current_iteration,
            iteration_budget=campaign.iteration_budget,
            risk_state=observation["risk_state"],
        )
        self.repository.record_decision(
            record["iteration_id"], decision["decision"], dataset["dataset_version_id"]
        )
        self._emit(
            campaign,
            "dataset_version_created",
            "经 Eligibility 与明确审批后创建了新的不可变 BO DatasetVersion。",
            {"dataset_version": dataset["dataset_version_id"], "sample_ids": dataset["sample_ids"]},
            f"dataset:{dataset['dataset_version_id']}",
        )
        self._emit(
            campaign,
            "trial_decision_made",
            f"确定性 TrialDecisionService 输出 {decision['decision']}。",
            decision,
            f"decision:{observation_id}",
        )
        if decision["decision"] == TrialDecision.CONTINUE_TRIAL.value:
            if not next_bo_result:
                raise ValueError("next_bo_result is required to continue the trial")
            result = dict(next_bo_result)
            result["dataset_version"] = dataset["dataset_version_id"]
            parent = self.recommendations.get(record["recommendation_id"])
            recommendation = self.recommendations.create(
                task_id=campaign.task_id,
                workflow_id=campaign.workflow_id,
                task_spec=campaign.task_spec,
                bo_result=result,
                search_space=campaign.search_space,
                current_recipe=parent["complete_recipe"],
                stage="trial_cut",
                parent_recommendation_id=parent["recommendation_id"],
                parameter_units=campaign.parameter_units,
                recommendation_source="bo_parameter_recommendation",
                source_run_id=result.get("bo_run_id") or result.get("source_run_id"),
            )
            iteration = TrialIteration(
                iteration_id=f"trial_iteration_{uuid.uuid4().hex}",
                campaign_id=campaign_id,
                iteration_number=campaign.current_iteration + 1,
                recommendation_id=recommendation.recommendation_id,
                parent_recommendation_id=parent["recommendation_id"],
                created_at=utc_now_iso(),
            )
            self.repository.save_iteration(iteration)
            campaign.current_iteration += 1
            campaign.current_recipe = dict(recommendation.complete_recipe)
            campaign.substatus = "TRIAL_RESULT_PENDING"
            self.repository.save_campaign(campaign)
            self._emit(
                campaign,
                "next_recommendation_created",
                f"基于新 DatasetVersion 创建 iteration {campaign.current_iteration} 完整 Recipe。",
                self._recommendation_event_payload(recommendation.to_dict()),
                f"recommendation:{recommendation.recommendation_id}",
            )
            cam = self.recommendations.cam_parameters(recommendation.recommendation_id)
            self._emit(
                campaign,
                "cam_export_created",
                "已生成下一轮试切 CAM 导出；系统未连接或控制设备。",
                {"recommendation_id": recommendation.recommendation_id},
                f"cam:{recommendation.recommendation_id}",
            )
            return {
                "decision": decision,
                "dataset_version": dataset,
                "next_iteration": iteration.to_dict(),
                "next_recommendation": recommendation.to_dict(),
                "cam_export": cam,
            }
        if decision["decision"] == TrialDecision.TRIAL_SUCCEEDED.value:
            candidate = self._create_production_candidate(campaign, record["recommendation_id"])
            return {
                "decision": decision,
                "dataset_version": dataset,
                "production_candidate": candidate,
            }
        campaign.substatus = decision["decision"]
        if decision["decision"] == TrialDecision.TRIAL_BLOCKED.value:
            self._transition(campaign, "BLOCKED")
        self.repository.save_campaign(campaign)
        return {"decision": decision, "dataset_version": dataset}

    def approve_production(
        self,
        campaign_id: str,
        candidate_id: str,
        *,
        approved_by: str,
    ) -> dict[str, Any]:
        if not approved_by:
            raise ValueError("approved_by is required")
        campaign = self.repository.get_campaign(campaign_id)
        if campaign.production_candidate_id != candidate_id:
            raise ValueError("candidate does not belong to this TrialCampaign")
        candidate = self.recommendations.get(candidate_id)
        approved = self.recommendations.create(
            task_id=campaign.task_id,
            workflow_id=campaign.workflow_id,
            task_spec=campaign.task_spec,
            bo_result={
                "recommended_parameters": candidate["optimized_parameters"],
                "model_status": candidate["confidence"].get("support_status"),
                "model_version": candidate.get("model_version"),
                "dataset_version": candidate.get("dataset_version"),
            },
            search_space=campaign.search_space,
            current_recipe=candidate["complete_recipe"],
            stage="production_approved",
            parent_recommendation_id=candidate_id,
            parameter_units=campaign.parameter_units,
            recommendation_source=candidate["recommendation_source"],
            source_run_id=candidate.get("source_run_id"),
        )
        campaign.production_approved_id = approved.recommendation_id
        self._transition(campaign, "FORMAL_PROCESS_READY")
        campaign.metadata["production_approved_by"] = approved_by
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "production_approved",
            "用户已明确批准正式加工候选；系统仍未连接或控制设备。",
            {"recommendation_id": approved.recommendation_id, "approved_by": approved_by},
            f"production-approved:{approved.recommendation_id}",
        )
        cam = self.recommendations.cam_parameters(approved.recommendation_id)
        self._emit(
            campaign,
            "cam_export_created",
            "已生成正式加工 CAM 导出；仅做格式映射，不执行设备控制。",
            {"recommendation_id": approved.recommendation_id},
            f"cam:{approved.recommendation_id}",
        )
        return {"campaign": campaign.to_dict(), "recommendation": approved.to_dict(), "cam_export": cam}

    def report_external_processing_started(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        self._transition(campaign, "FORMAL_PROCESS_RUNNING")
        campaign.metadata["external_status_source"] = "user_reported"
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "external_processing_reported",
            "用户上报外部加工已开始；系统未读取、控制或监控设备。",
            {"source": "user_reported"},
            "external-processing-started",
        )
        return campaign.to_dict()

    def submit_final_inspection(
        self,
        campaign_id: str,
        *,
        measurements: dict[str, Any],
        constraint_results: dict[str, bool],
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        self._transition(campaign, "FINAL_INSPECTION_PENDING")
        self._emit(
            campaign,
            "final_inspection_received",
            "已接收用户上报的最终检测结果。",
            {"measurement_names": sorted(measurements), "file_count": len(files or [])},
            "final-inspection",
        )
        decision = self._quality_decision(measurements, campaign.targets, constraint_results)
        if decision == "PASS":
            self._transition(campaign, "COMPLETED")
        elif decision == "MINOR_DRIFT":
            self._transition(campaign, "BO_READY")
        else:
            self._transition(campaign, "TRIAL_ASSESSMENT")
        campaign.metadata["quality_decision"] = decision
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "quality_decision_made",
            f"确定性质量判定为 {decision}。",
            {"decision": decision, "constraint_results": constraint_results},
            "quality-decision",
        )
        report = None
        if decision == "PASS":
            report = TaskReportService().generate(campaign.task_id, {
                "task_spec": campaign.task_spec,
                "trial_result": {"iterations": self.repository.list_iterations(campaign_id)},
                "quality_plan": {"decision": decision, "measurements": measurements},
                "bo": {"dataset_version": campaign.metadata.get("dataset_version")},
                "business_state": BusinessState.COMPLETED.value,
                "substatus": "COMPLETED",
                "next_step": "archived",
            })
        return {
            "campaign": campaign.to_dict(),
            "quality_decision": decision,
            "report": report,
        }

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        run_id = self._run_id(campaign)
        return {
            "campaign": campaign.to_dict(),
            "iterations": self.repository.list_iterations(campaign_id),
            "events": RuntimeEventRepository().list_run_events(run_id),
        }

    def _create_production_candidate(
        self, campaign: TrialCampaign, parent_recommendation_id: str
    ) -> dict[str, Any]:
        parent = self.recommendations.get(parent_recommendation_id)
        candidate = self.recommendations.create(
            task_id=campaign.task_id,
            workflow_id=campaign.workflow_id,
            task_spec=campaign.task_spec,
            bo_result={
                "recommended_parameters": parent["optimized_parameters"],
                "model_status": parent["confidence"].get("support_status"),
                "model_version": parent.get("model_version"),
                "dataset_version": campaign.metadata.get("dataset_version"),
            },
            search_space=campaign.search_space,
            current_recipe=parent["complete_recipe"],
            stage="production_candidate",
            parent_recommendation_id=parent_recommendation_id,
            parameter_units=campaign.parameter_units,
            recommendation_source=parent["recommendation_source"],
            source_run_id=parent.get("source_run_id"),
        )
        campaign.production_candidate_id = candidate.recommendation_id
        self._transition(campaign, "TRIAL_RESULT_EVALUATION")
        campaign.substatus = "PRODUCTION_CANDIDATE_PENDING_APPROVAL"
        self.repository.save_campaign(campaign)
        self._emit(
            campaign,
            "production_candidate_created",
            "试切目标达到，已生成等待用户批准的正式加工候选。",
            self._recommendation_event_payload(candidate.to_dict()),
            f"production-candidate:{candidate.recommendation_id}",
        )
        return candidate.to_dict()

    @staticmethod
    def _select_parameter_source(
        options: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], str]:
        for key, source in SOURCE_ORDER:
            value = options.get(key) or {}
            if value.get("recommended_parameters") and value.get("status") != "blocked":
                return dict(value), source
        raise ValueError("no governed parameter recommendation source is available")

    @staticmethod
    def _validate_feedback(
        campaign: TrialCampaign,
        recommendation: dict[str, Any],
        feedback: dict[str, Any],
    ) -> None:
        required_maps = (
            "cam_applied_parameters",
            "machine_actual_parameters",
            "measurements",
            "parameter_units",
            "measurement_units",
        )
        missing = [name for name in required_maps if not feedback.get(name)]
        if missing:
            raise ValueError(f"feedback fields required: {missing}")
        recipe_keys = set(recommendation["complete_recipe"])
        for field in ("cam_applied_parameters", "machine_actual_parameters"):
            absent = recipe_keys - set(feedback[field])
            if absent:
                raise ValueError(f"{field} missing complete Recipe parameters: {sorted(absent)}")
        if set(feedback["machine_actual_parameters"]) - set(feedback["parameter_units"]):
            raise ValueError("machine actual parameter units are incomplete")
        if set(feedback["measurements"]) - set(feedback["measurement_units"]):
            raise ValueError("measurement units are incomplete")
        for name, metadata in recommendation["parameter_metadata"].items():
            expected = metadata.get("unit")
            actual = feedback["parameter_units"].get(name)
            if expected and actual != expected:
                raise ValueError(f"parameter unit mismatch for {name}: {actual} != {expected}")
        if feedback.get("material") != campaign.task_spec["material"]:
            raise ValueError("feedback material does not match canonical TaskSpec")
        if feedback.get("process_type") != campaign.task_spec["process_type"]:
            raise ValueError("feedback process_type does not match canonical TaskSpec")
        if feedback.get("equipment_revision") != campaign.equipment_revision:
            raise ValueError("feedback equipment revision mismatch")

    @staticmethod
    def _actual_out_of_bounds(
        actual: dict[str, Any],
        recommended: dict[str, Any],
        search_space: dict[str, Any],
    ) -> bool:
        for name, raw in actual.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                return True
            variable = (search_space.get("variables") or {}).get(name) or {}
            if variable.get("lower") is not None and float(raw) < float(variable["lower"]):
                return True
            if variable.get("upper") is not None and float(raw) > float(variable["upper"]):
                return True
            expected = recommended.get(name)
            if isinstance(expected, (int, float)):
                tolerance = max(abs(float(expected)) * 0.5, 1e-9)
                if abs(float(raw) - float(expected)) > tolerance:
                    return True
        return False

    @staticmethod
    def _quality_decision(
        measurements: dict[str, Any],
        targets: dict[str, Any],
        constraints: dict[str, bool],
    ) -> str:
        if not measurements or any(value is False for value in constraints.values()):
            return "FAIL"
        if set(targets) - set(measurements):
            return "FAIL"
        passed = all(
            TrialDecisionService._target_met(float(measurements[name]), target)
            for name, target in targets.items()
        )
        return "PASS" if passed else "MINOR_DRIFT"

    @staticmethod
    def _transition(campaign: TrialCampaign, substatus: str) -> None:
        state = {
            "business_state": campaign.business_state,
            "substatus": campaign.substatus,
            "state": campaign.substatus,
        }
        BusinessStateController.transition(state, substatus)
        campaign.business_state = state["business_state"]
        campaign.substatus = substatus

    def _emit(
        self,
        campaign: TrialCampaign,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
        idempotency_suffix: str,
    ) -> dict[str, Any]:
        event = canonical_agent_events.emit(
            run_id=self._run_id(campaign),
            session_id=campaign.metadata.get("session_id"),
            message_id=None,
            workflow_id=campaign.workflow_id,
            event_type=event_type,
            stage=campaign.business_state,
            step=campaign.substatus,
            title=event_type.replace("_", " ").title(),
            public_summary=summary,
            status="completed",
            payload=payload,
            idempotency_key=f"{campaign.campaign_id}:{idempotency_suffix}",
        )
        return event.to_dict()

    @staticmethod
    def _run_id(campaign: TrialCampaign) -> str:
        return f"trial-campaign-run:{campaign.campaign_id}"

    @staticmethod
    def _recommendation_event_payload(value: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "recommendation_id",
            "iteration_number",
            "parent_recommendation_id",
            "complete_recipe",
            "optimized_parameters",
            "fixed_parameters",
            "forbidden_parameters",
            "constraints",
            "recommendation_source",
            "source_run_id",
            "model_version",
            "dataset_version",
            "evidence_ids",
        )
        return {key: value.get(key) for key in keys}
