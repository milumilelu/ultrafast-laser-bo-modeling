from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_domain.trial import TrialMode, design_trial_plan
from ultrafast_integrations.storage.demo_fixture_repository import DemoFixtureRepository
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile
from ultrafast_memory.reports.task_report_service import TaskReportService


class DemoService:
    """Offline fixture demo; it deliberately does not exercise a second workflow controller."""

    def __init__(self):
        self.fixtures = DemoFixtureRepository()
        self.reports = TaskReportService()

    def run_tgv(self, approve_review: bool = False, selected_trial_mode: str | None = None) -> dict[str, Any]:
        try:
            fixture = self.fixtures.ensure_tgv_evidence()
        except sqlite3.OperationalError as exc:
            if "readonly" not in str(exc).lower() and "read-only" not in str(exc).lower():
                raise
            return self._read_only_fallback(exc)
        equipment = self._ensure_equipment()
        task_id = f"demo-tgv-{uuid.uuid4().hex[:10]}"
        if not selected_trial_mode:
            return {"status": "waiting_trial_mode", "task_id": task_id,
                    "next_required_action": "select_trial_mode", "fixture": fixture,
                    "external_network": False, "llm_call_performed": False}
        task = self._task(task_id)
        plan = design_trial_plan(task_id, task, TrialMode(selected_trial_mode),
                                 equipment["machine_bounds"], "tgv").to_dict()
        if not approve_review:
            return {"status": "waiting_review", "task_id": task_id,
                    "approval_card": {"actions": ["approve_task", "approve_prior", "reject"]},
                    "trial_plan": plan, "fixture": fixture,
                    "external_network": False, "llm_call_performed": False}
        bo = LegacyBOCompatibilityAdapter().recommend(task, [], equipment)
        evaluation = {"decision": "pass", "basis": "deterministic_demo_fixture"}
        report = self.reports.generate(task_id, {
            "task_spec": task, "equipment_snapshot": equipment, "trial_plan": plan,
            "trial_result": {"evaluation": evaluation}, "bo_recommendation": bo,
            "formal_execution": {"status": "ready"}, "next_step": "ready",
        })
        return {"status": "completed", "task_id": task_id, "fixture": fixture,
                "bo": bo, "trial_result": {"evaluation": evaluation},
                "formal_execution": {"status": "ready"}, "report": report,
                "external_network": False, "llm_call_performed": False}

    def _read_only_fallback(self, error: Exception) -> dict[str, Any]:
        machine = {"active": True, "revision_id": "read-only-demo-equipment-v1", "machine_bounds": {}}
        trial = design_trial_plan("read-only-demo-tgv", self._task("read-only-demo-tgv"),
                                  TrialMode.SIMPLE, machine["machine_bounds"], "tgv").to_dict()
        return {"status": "read_only_demo", "task_id": "read-only-demo-tgv", "read_only": True,
                "persistence_performed": False, "failure_type": type(error).__name__,
                "knowledge_gate": {"status": "blocked", "reasons": ["review_persistence_unavailable"]},
                "trial_plan": trial, "formal_execution": {"status": "blocked_read_only_demo",
                                                             "formal_process_unlocked": False},
                "external_network": False, "llm_call_performed": False}

    @staticmethod
    def _task(task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "material": "glass_wafer", "component_type": "TGV_array",
                "process_type": "TGV_drilling", "geometry": {"wafer_thickness_um": 500,
                "hole_diameter_um": 50, "pitch_um": 100}, "targets": {"depth_min_um": 450}}

    @staticmethod
    def _ensure_equipment() -> dict[str, Any]:
        current = build_machine_bounds()
        if current.get("active") and not current.get("missing_equipment_fields"):
            return current
        create_equipment_profile(EquipmentProfileCreate(
            profile_name="Offline Demo Femtosecond Laser", machine_id="demo-machine",
            laser_source={"wavelength_nm": 1030, "pulse_width_min_fs": 300, "pulse_width_max_fs": 1000,
                          "average_power_min_W": 1, "average_power_max_W": 20,
                          "frequency_min_kHz": 50, "frequency_max_kHz": 500},
            optical_setup={"spot_diameter_um": 20, "focus_offset_min_um": -50, "focus_offset_max_um": 50},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 1000},
            process_capability={"hatch_spacing_min_um": 2, "hatch_spacing_max_um": 20,
                                "layer_step_min_um": 1, "layer_step_max_um": 20,
                                "passes_min": 1, "passes_max": 20},
            created_by="demo_fixture", set_active=True,
        ))
        return build_machine_bounds()
