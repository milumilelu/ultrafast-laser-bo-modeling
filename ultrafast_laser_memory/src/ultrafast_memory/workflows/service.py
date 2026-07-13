from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterator

from ultrafast_agent.runtime import AgentRuntime, EventBus, RunContext, ToolContract, ToolRegistry
from ultrafast_agent.workflows import get_workflow
from ultrafast_bo import BOStatusService
from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_domain.domain_packs import load_domain_pack
from ultrafast_domain.trial import assess_trial_need, select_trial_mode
from ultrafast_integrations.storage.read_models import (
    find_similar_process_cases,
    list_bo_training_samples,
)
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.knowledge_use.service import KnowledgeUseApplicationService
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.trial.service import TrialApplicationService
from ultrafast_memory.process_workflow.evidence import credibility_summary


class TaskWorkflowService:
    def __init__(self):
        self.events = RuntimeEventRepository()
        self.trials = TrialApplicationService()
        self.knowledge = KnowledgeUseApplicationService()

    def execute(self, workflow_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        context = self._context(payload)
        runner = self._runner(context)
        result = runner.execute(get_workflow(workflow_name), context)
        return asdict(result)

    def stream(self, workflow_name: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        context = self._context(payload)
        runner = self._runner(context)
        yield from runner.stream(get_workflow(workflow_name), context)

    def get_trace(self, run_id: str) -> list[dict[str, Any]]:
        return self.events.list_run_events(run_id)

    def _context(self, payload: dict[str, Any]) -> RunContext:
        task_id = payload["task_id"]
        data = {
            **(payload.get("context") or {}),
            "task_id": task_id,
            "input_task_spec": {"task_id": task_id, **(payload.get("task_spec") or {})},
            "input_equipment_snapshot": payload.get("equipment_snapshot"),
            "question": payload.get("question"),
            "selected_trial_mode": payload.get("selected_trial_mode"),
            "trial_result_validated": bool(payload.get("trial_result_validated")),
            "archive_ready": bool(payload.get("archive_ready")),
            "approved_parameter_candidates": payload.get("approved_parameter_candidates") or [],
            "intended_use": payload.get("intended_use", "parameter_recommendation"),
            "session_id": payload.get("session_id"),
        }
        return RunContext(
            data=data,
            session_id=payload.get("session_id"),
            task_id=task_id,
            display_mode=payload.get("display_mode", "normal"),
        )

    def _runner(self, context: RunContext) -> AgentRuntime:
        registry = self._registry()

        def factory(run_id: str) -> EventBus:
            bus = EventBus(
                run_id, session_id=context.session_id, task_id=context.task_id
            )
            bus.subscribe(
                lambda event: self.events.persist(
                    event, session_id=context.session_id, task_id=context.task_id
                )
            )
            return bus

        return AgentRuntime(registry, event_bus_factory=factory)

    def _registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        handlers = {
            "task_intake": ("Normalize the structured task input", self._task_intake),
            "material_identification": ("Identify material without inventing properties", self._material),
            "equipment_context_loading": ("Load authoritative equipment context", self._equipment),
            "geometry_interpretation": ("Interpret geometry using a domain pack", self._geometry),
            "constraint_extraction": ("Extract hard and soft constraints", self._constraints),
            "load_domain_pack": ("Load process domain rules", self._load_pack),
            "domain_geometry_check": ("Validate domain-specific geometry", self._geometry),
            "density_and_pitch_check": ("Check microhole density and pitch", self._density_pitch),
            "rag_evidence_retrieval": ("Query the internal literature index", self._rag),
            "similar_case_retrieval": ("Retrieve comparable completed process cases", self._similar),
            "process_route_planning": ("Construct a bounded process route", self._route),
            "process_risk_assessment": ("Assess process risks", self._risk),
            "trial_need_assessment": ("Assess required trial depth", self._trial_assess),
            "trial_strategy_selection": ("Select an allowed trial mode", self._trial_select),
            "simple_trial_design": ("Persist a simple representative trial plan", self._trial_design),
            "full_trial_design": ("Persist a full-geometry trial plan", self._trial_design),
            "knowledge_use_gate": ("Evaluate knowledge use and approval requirements", self._knowledge_gate),
            "bo_mode_selection": ("Select BO mode from validated samples", self._bo_status),
            "bo_recommendation": ("Call the real bounded BO service", self._bo_recommend),
            "quality_plan_generation": ("Build a domain-aware quality plan", self._quality),
            "measurement_plan_generation": ("Build a domain-aware measurement plan", self._measurement),
            "toolpath_strategy_selection": ("Select a non-machine-control toolpath strategy", self._toolpath),
            "in_process_monitoring_plan": ("Build public monitoring and stop conditions", self._monitoring),
            "execution_plan_generation": ("Build or block the formal execution plan", self._execution),
            "report_generation": ("Aggregate structured task-report inputs", self._report),
        }
        for name, (purpose, handler) in handlers.items():
            registry.register(ToolContract(name, purpose, handler))
        return registry

    def _task_intake(self, payload: dict, context: dict) -> dict:
        task = dict(context["input_task_spec"])
        missing = [name for name in ("material", "component_type", "process_type") if not task.get(name)]
        task["missing_fields"] = missing
        task["can_continue_to_planning"] = not missing
        return task

    def _equipment(self, payload: dict, context: dict) -> dict:
        return context.get("input_equipment_snapshot") or build_machine_bounds()

    def _material(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or context.get("input_task_spec") or {}
        return {"material": task.get("material"), "grade": task.get("material_grade"),
                "batch": task.get("material_batch"), "status": "identified" if task.get("material") else "missing"}

    def _constraints(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        return {"hard_constraints": task.get("hard_constraints") or task.get("quality_requirements") or [],
                "soft_constraints": task.get("soft_constraints") or [], "equipment_bounds_are_process_parameters": False}

    def _risk(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        material = str(task.get("material") or "").lower()
        risks = ["delamination", "thermal_accumulation"] if "cfrp" in material or "carbon" in material else ["equipment_boundary", "quality_nonconformance"]
        return {"risks": risks, "requires_trial": True, "formal_parameters_authorized": False}

    def _pack_name(self, context: dict) -> str:
        task = context.get("task_spec") or context.get("input_task_spec") or {}
        explicit = task.get("domain_pack")
        if explicit:
            return explicit
        text = " ".join(str(task.get(key) or "") for key in ("component_type", "process_type", "material")).lower()
        if "crl" in text or "lens" in text or "透镜" in text:
            return "crl"
        if "tgv" in text or "through_glass" in text or "玻璃通孔" in text:
            return "tgv"
        if "cooling" in text or "气膜" in text:
            return "film_cooling_hole"
        if "cover_glass" in text or "盖板玻璃" in text:
            return "cover_glass"
        return "surface_texturing"

    def _load_pack(self, payload: dict, context: dict) -> dict:
        pack = load_domain_pack(self._pack_name(context))
        return {
            "name": pack.name,
            "component_types": list(pack.component_types),
            "quality_metrics": list(pack.quality_metrics),
            "process_constraints": list(pack.process_constraints),
            "trial_templates": pack.trial_templates,
            "measurement_templates": pack.measurement_templates,
        }

    def _geometry(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        pack = load_domain_pack(self._pack_name(context))
        geometry = task.get("geometry") or {}
        return {"domain_pack": pack.name, **pack.validate_geometry(geometry)}

    def _density_pitch(self, payload: dict, context: dict) -> dict:
        geometry = (context.get("task_spec") or {}).get("geometry") or {}
        pitch = geometry.get("pitch_um")
        diameter = geometry.get("hole_diameter_um")
        valid = pitch is not None and diameter is not None and float(pitch) > float(diameter)
        return {"valid": valid, "pitch_um": pitch, "hole_diameter_um": diameter, "reason": "pitch must exceed diameter"}

    def _rag(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        query = context.get("question") or " ".join(
            str(task.get(key) or "") for key in ("material", "component_type", "process_type")
        )
        result = query_rag({"query": query.strip() or "ultrafast laser process", "top_k": 8})
        result["credibility_summary"] = credibility_summary(result.get("hits") or [], task)
        result["evidence_status"] = result["credibility_summary"]["evidence_status"]
        return result

    def _similar(self, payload: dict, context: dict) -> dict:
        cases = find_similar_process_cases(context.get("task_spec") or {})
        return {"cases": cases, "count": len(cases)}

    def _route(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        return {
            "steps": ["prepare", "trial", "measure", "review", "optimize", "formal_process"],
            "process_type": task.get("process_type"),
            "domain_pack": self._pack_name(context),
            "status": "planned",
        }

    def _trial_assess(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        evidence = context.get("evidence_pack") or {}
        samples = list_bo_training_samples()
        assessment = assess_trial_need(
            task,
            evidence_status=evidence.get("evidence_status", "insufficient"),
            approved_prior_count=int(context.get("approved_prior_count", 0)),
            similar_case_count=int((context.get("similar_cases") or {}).get("count", 0)),
            valid_sample_count=len(samples),
            equipment_revision_unchanged=bool(context.get("equipment_revision_unchanged", False)),
        )
        return assessment.to_dict()

    def _trial_select(self, payload: dict, context: dict) -> dict:
        assessment = context.get("trial_assessment")
        if not assessment:
            assessment = assess_trial_need(
                context.get("task_spec") or {},
                evidence_status=(context.get("evidence_pack") or {}).get("evidence_status", "insufficient"),
                valid_sample_count=len(list_bo_training_samples()),
            ).to_dict()
        selected = context.get("selected_trial_mode")
        if not selected:
            return {
                "status": "TRIAL_MODE_PENDING",
                "trial_mode": None,
                "recommended_mode": assessment["recommended_mode"],
                "allowed_modes": ["simple_trial_cut", "full_trial_cut", "skip_trial"],
                "next_required_action": {
                    "action_type": "select_trial_mode",
                    "allowed_values": ["simple_trial_cut", "full_trial_cut", "skip_trial"],
                    "blocking": True,
                },
            }
        mode = select_trial_mode(assessment, selected)
        return {"trial_mode": mode.value, "recommended_mode": assessment["recommended_mode"], "user_overrode": mode.value != assessment["recommended_mode"]}

    def _trial_design(self, payload: dict, context: dict) -> dict:
        task = context.get("task_spec") or {}
        selection = context.get("trial_selection") or {}
        return self.trials.create_plan(
            context["task_id"],
            {
                "task_spec": task,
                "trial_mode": selection["trial_mode"],
                "machine_bounds": (context.get("equipment_snapshot") or {}).get("machine_bounds") or {},
                "domain_pack": self._pack_name(context),
                "approved_parameter_candidates": context.get("approved_parameter_candidates") or [],
            },
        )

    def _knowledge_gate(self, payload: dict, context: dict) -> dict:
        evidence_pack = context.get("evidence_pack") or {}
        evidence = [
            {
                "evidence_id": hit.get("chunk_id"),
                "source_revision": hit.get("paper_id"),
                "claim_revision": hit.get("chunk_id"),
                "claim": hit.get("content"),
                "status": hit.get("review_status"),
                "conflict_flag": False,
            }
            for hit in (evidence_pack.get("hits") or [])[:5]
        ]
        return self.knowledge.evaluate(
            context["task_id"],
            {
                "session_id": context.get("session_id"),
                "task_spec": context.get("task_spec") or {},
                "intended_use": context.get("intended_use", "parameter_recommendation"),
                "evidence": evidence,
                "equipment": context.get("equipment_snapshot") or {},
                "proposed_usage": {"parameters": context.get("proposed_literature_parameters") or []},
            },
        )

    def _bo_status(self, payload: dict, context: dict) -> dict:
        return BOStatusService().get_status(list_bo_training_samples())

    def _bo_recommend(self, payload: dict, context: dict) -> dict:
        task = dict(context.get("task_spec") or {})
        evidence_count = len((context.get("evidence_pack") or {}).get("hits") or [])
        if evidence_count:
            task["literature_parameters_used"] = True
            task["knowledge_gate_decision"] = context.get("knowledge_gate_decision") or {}
        return LegacyBOCompatibilityAdapter().recommend(
            task,
            list_bo_training_samples(),
            context.get("equipment_snapshot") or {},
            context.get("approved_priors") or [],
        )

    def _quality(self, payload: dict, context: dict) -> dict:
        pack = load_domain_pack(self._pack_name(context))
        return {"metrics": list(pack.quality_metrics), "acceptance_source": "task_targets_and_domain_pack", "traceability_required": True}

    def _measurement(self, payload: dict, context: dict) -> dict:
        pack = load_domain_pack(self._pack_name(context))
        return {"templates": pack.measurement_templates, "traceability_required": True}

    def _toolpath(self, payload: dict, context: dict) -> dict:
        return {"strategy": "domain_pack_geometry_aware", "domain_pack": self._pack_name(context), "machine_control": False}

    def _monitoring(self, payload: dict, context: dict) -> dict:
        return {"signals": ["energy_drift", "temperature", "depth", "crack_growth", "equipment_alarm"], "action": "stop_and_record"}

    def _execution(self, payload: dict, context: dict) -> dict:
        unlocked = bool(context.get("formal_process_unlocked"))
        return {
            "status": "ready" if unlocked else "blocked_pending_trial",
            "formal_process_unlocked": unlocked,
            "machine_control": False,
            "route": context.get("process_route"),
            "recommendation": context.get("bo_recommendation"),
        }

    def _report(self, payload: dict, context: dict) -> dict:
        return {
            "task_id": context["task_id"],
            "task_spec": context.get("task_spec"),
            "equipment": context.get("equipment_snapshot"),
            "evidence_status": (context.get("evidence_pack") or {}).get("evidence_status"),
            "process_route": context.get("process_route"),
            "trial": context.get("trial_plan") or context.get("trial_selection"),
            "knowledge_gate": context.get("knowledge_gate_decision"),
            "bo": context.get("bo_recommendation") or context.get("bo_status"),
            "quality_plan": context.get("quality_plan"),
            "execution_plan": context.get("execution_plan"),
        }
