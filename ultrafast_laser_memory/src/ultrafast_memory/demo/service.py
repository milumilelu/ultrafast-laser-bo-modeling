from __future__ import annotations

import uuid
import sqlite3
from typing import Any

from ultrafast_integrations.storage.demo_fixture_repository import DemoFixtureRepository
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile
from ultrafast_memory.knowledge_use.service import KnowledgeUseApplicationService
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.trial.service import TrialApplicationService
from ultrafast_memory.workflows.service import TaskWorkflowService


class DemoService:
    def __init__(self):
        self.fixtures = DemoFixtureRepository()
        self.workflows = TaskWorkflowService()
        self.knowledge = KnowledgeUseApplicationService()
        self.trials = TrialApplicationService()
        self.reports = TaskReportService()

    def run_tgv(self, approve_review: bool = False, selected_trial_mode: str | None = None) -> dict[str, Any]:
        try:
            fixture = self.fixtures.ensure_tgv_evidence()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "readonly" not in message and "read-only" not in message:
                raise
            return self._read_only_fallback(exc)
        equipment = self._ensure_equipment()
        task_id = f"demo-tgv-{uuid.uuid4().hex[:10]}"
        request = self._request(task_id, equipment)
        if not selected_trial_mode:
            preview = self.workflows.execute("complex_process_task", request)
            return {"status": "waiting_trial_mode", "task_id": task_id,
                    "next_required_action": preview["data"]["trial_selection"]["next_required_action"],
                    "workflow": preview, "fixture": fixture, "external_network": False,
                    "llm_call_performed": False}
        request["selected_trial_mode"] = selected_trial_mode
        first = self.workflows.execute("complex_process_task", request)
        plan = first["data"]["trial_plan"]
        execution = self.trials.start_execution(
            plan["trial_plan_id"],
            {"equipment_revision": equipment["revision_id"],
             "actual_parameters": (plan.get("parameter_matrix") or [{}])[0],
             "actual_path": {"type": plan["representative_geometry"]["type"], "demo_fixture": True},
             "monitoring_summary": {"abnormal": False, "demo_fixture": True}},
        )
        result = self.trials.create_result(execution["execution_id"], {
            "measurements": {"depth_um": 500, "taper_deg": 2.0, "crack_length_um": 0.0,
                             "through_rate": 1.0, "yield": 1.0}, "defects": []})
        evaluated = self.trials.evaluate(result["result_id"], {
            "reviewer_comment": "Deterministic demo fixture result", "confirm_conditional": False})
        reviewed_request = {**request, "trial_result_validated": True}
        reviewed = self.workflows.execute("complex_process_task", reviewed_request)
        gate = reviewed["data"].get("knowledge_gate_decision") or {}
        if gate.get("status") == "approval_required" and not approve_review:
            return {
                "status": "waiting_review",
                "task_id": task_id,
                "decision_id": gate.get("decision_id"),
                "approval_card": {
                    "actions": ["approve_task", "approve_prior", "reject"],
                    "risk_level": gate.get("risk_level"),
                    "evidence_ids": gate.get("evidence_ids"),
                },
                "workflow": reviewed,
                "fixture": fixture,
                "external_network": False,
                "llm_call_performed": False,
            }
        if gate.get("status") == "approval_required":
            self.knowledge.approve_task(
                gate["decision_id"],
                {
                    "reviewer_id": "demo-human-confirmation",
                    "comment": "Explicit Demo Mode task-scoped approval",
                    "approved_payload": {},
                },
            )
        planned = self.workflows.execute("complex_process_task", reviewed_request)
        bo = planned["data"].get("bo_recommendation") or {}
        final_request = {
            **reviewed_request,
            "archive_ready": True,
            "context": {"formal_process_unlocked": evaluated["formal_process_decision"]["unlocked"]},
        }
        final = self.workflows.execute("complex_process_task", final_request)
        report = self.reports.generate(
            task_id,
            {
                **final["data"],
                "trial_plan": plan,
                "trial_result": evaluated,
                "bo_recommendation": bo,
                "risks": ["demo_fixture_not_machine_execution"],
                "next_step": final["data"]["execution_plan"]["status"],
            },
            final["run_id"],
        )
        return {
            "status": "completed",
            "task_id": task_id,
            "fixture": fixture,
            "knowledge_gate": planned["data"].get("knowledge_gate_decision"),
            "bo": bo,
            "trial_result": evaluated,
            "formal_execution": final["data"]["execution_plan"],
            "report": report,
            "external_network": False,
            "llm_call_performed": False,
            "demo_fixture": True,
        }

    def _read_only_fallback(self, error: Exception) -> dict[str, Any]:
        from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
        from ultrafast_domain.trial import design_trial_plan

        machine = {
            "active": True,
            "revision_id": "read-only-demo-equipment-v1",
            "machine_bounds": {
                "laser_power_W": [1.0, 20.0],
                "frequency_kHz": [50.0, 500.0],
                "scan_speed_mm_s": [10.0, 1000.0],
                "passes": [1, 20],
            },
        }
        trial = design_trial_plan(
            "read-only-demo-tgv",
            {
                "material": "glass_wafer",
                "component_type": "TGV_array",
                "process_type": "TGV_drilling",
                "targets": {"depth_min_um": 450},
            },
            "simple_trial_cut",
            machine["machine_bounds"],
            "tgv",
        ).to_dict()
        bo = LegacyBOCompatibilityAdapter().recommend({}, [], machine)
        return {
            "status": "read_only_demo",
            "task_id": "read-only-demo-tgv",
            "read_only": True,
            "persistence_performed": False,
            "external_network": False,
            "llm_call_performed": False,
            "failure_type": type(error).__name__,
            "evidence_status": "unavailable_read_only",
            "knowledge_gate": {
                "status": "blocked",
                "reasons": ["review_persistence_unavailable"],
            },
            "bo": bo,
            "trial_plan": trial,
            "formal_execution": {
                "status": "blocked_read_only_demo",
                "formal_process_unlocked": False,
                "machine_control": False,
            },
            "report": None,
            "warnings": [
                "Read-only Demo is a non-persistent preview; no approval, result, or report was written."
            ],
        }

    def _ensure_equipment(self) -> dict[str, Any]:
        current = build_machine_bounds()
        if current.get("active") and not current.get("missing_equipment_fields"):
            return current
        create_equipment_profile(
            EquipmentProfileCreate(
                profile_name="Offline Demo Femtosecond Laser",
                machine_id="demo-machine",
                laser_source={
                    "wavelength_nm": 1030,
                    "pulse_width_min_fs": 300,
                    "pulse_width_max_fs": 1000,
                    "average_power_min_W": 1,
                    "average_power_max_W": 20,
                    "frequency_min_kHz": 50,
                    "frequency_max_kHz": 500,
                },
                optical_setup={"spot_diameter_um": 20, "focus_offset_min_um": -50, "focus_offset_max_um": 50},
                motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 1000},
                process_capability={
                    "hatch_spacing_min_um": 2,
                    "hatch_spacing_max_um": 20,
                    "layer_step_min_um": 1,
                    "layer_step_max_um": 20,
                    "passes_min": 1,
                    "passes_max": 20,
                },
                created_by="demo_fixture",
                set_active=True,
            )
        )
        return build_machine_bounds()

    def _request(self, task_id: str, equipment: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "session_id": f"session-{task_id}",
            "task_spec": {
                "objective": "Demonstrate a traceable high-aspect-ratio TGV process plan",
                "material": "glass_wafer",
                "material_grade": "TGV",
                "component_type": "TGV_array",
                "process_type": "TGV_drilling",
                "domain_pack": "tgv",
                "geometry": {"wafer_thickness_um": 500, "hole_diameter_um": 50, "pitch_um": 100},
                "targets": {"depth_min_um": 450},
                "first_material": True,
            },
            "equipment_snapshot": equipment,
            "question": "TGV high aspect ratio glass via femtosecond laser drilling parameter range",
            "intended_use": "parameter_recommendation",
            "display_mode": "research",
        }
