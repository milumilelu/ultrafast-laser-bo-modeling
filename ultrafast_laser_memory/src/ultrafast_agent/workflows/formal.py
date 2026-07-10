from __future__ import annotations

from ultrafast_agent.runtime.workflow import WorkflowDefinition, WorkflowStep


def _bo_fallback(error: Exception, data: dict) -> dict:
    equipment = data.get("equipment_snapshot") or {}
    return {
        "model_status": "blocked",
        "bo_invoked": False,
        "recommended_parameters": {},
        "search_space": equipment.get("machine_bounds") or {},
        "machine_bounds_revision": equipment.get("revision_id"),
        "warnings": [f"BO unavailable: {type(error).__name__}"],
        "audit_trace": [{"step": "bo_runtime", "status": "fallback"}],
    }


def complex_process_task() -> WorkflowDefinition:
    return WorkflowDefinition(
        "complex_process_task",
        (
            WorkflowStep("task_intake", "task_intake", output_key="task_spec", skill="task_intake"),
            WorkflowStep("equipment_context_loading", "equipment_context_loading", output_key="equipment_snapshot", skill="equipment_context_loading", parallel_group="context_prefetch"),
            WorkflowStep("geometry_interpretation", "geometry_interpretation", output_key="geometry_model", skill="geometry_interpretation", parallel_group="context_prefetch"),
            WorkflowStep("rag_evidence_retrieval", "rag_evidence_retrieval", output_key="evidence_pack", timeout_ms=10000, skill="rag_evidence_retrieval", parallel_group="context_prefetch"),
            WorkflowStep("similar_case_retrieval", "similar_case_retrieval", output_key="similar_cases", skill="similar_case_retrieval", parallel_group="context_prefetch"),
            WorkflowStep("process_route_planning", "process_route_planning", output_key="process_route", skill="process_route_planning"),
            WorkflowStep("trial_need_assessment", "trial_need_assessment", output_key="trial_assessment", skill="trial_need_assessment"),
            WorkflowStep("trial_strategy_selection", "trial_strategy_selection", output_key="trial_selection", skill="trial_strategy_selection"),
            WorkflowStep(
                "simple_trial_design",
                "simple_trial_design",
                output_key="trial_plan",
                condition=lambda data: (data.get("trial_selection") or {}).get("trial_mode") == "simple_trial_cut",
                skill="simple_trial_design",
            ),
            WorkflowStep(
                "full_trial_design",
                "full_trial_design",
                output_key="trial_plan",
                condition=lambda data: (data.get("trial_selection") or {}).get("trial_mode") == "full_trial_cut",
                skill="full_trial_design",
            ),
            WorkflowStep("knowledge_use_gate", "knowledge_use_gate", output_key="knowledge_gate_decision", skill="knowledge_use_gate"),
            WorkflowStep("bo_mode_selection", "bo_mode_selection", output_key="bo_status", skill="bo_mode_selection"),
            WorkflowStep(
                "bo_recommendation",
                "bo_recommendation",
                output_key="bo_recommendation",
                condition=lambda data: (data.get("knowledge_gate_decision") or {}).get("status") == "allowed",
                timeout_ms=3000,
                skill="bo_recommendation",
                fallback_builder=_bo_fallback,
            ),
            WorkflowStep("quality_plan_generation", "quality_plan_generation", output_key="quality_plan", skill="quality_plan_generation"),
            WorkflowStep("execution_plan_generation", "execution_plan_generation", output_key="execution_plan", skill="execution_plan_generation"),
            WorkflowStep("report_generation", "report_generation", output_key="task_report", skill="report_generation"),
        ),
    )


def optical_component_task_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        "optical_component_task_workflow",
        (
            WorkflowStep("task_intake", "task_intake", output_key="task_spec", skill="task_intake"),
            WorkflowStep("equipment_context_loading", "equipment_context_loading", output_key="equipment_snapshot", skill="equipment_context_loading", parallel_group="optical_context"),
            WorkflowStep("geometry_interpretation", "geometry_interpretation", output_key="geometry_model", skill="geometry_interpretation", parallel_group="optical_context"),
            WorkflowStep("load_domain_pack", "load_domain_pack", output_key="domain_pack", skill="geometry_interpretation", parallel_group="optical_context"),
            WorkflowStep("dual_paraboloid_constraint_check", "domain_geometry_check", output_key="domain_geometry_check", skill="equipment_capability_match"),
            WorkflowStep("process_route_planning", "process_route_planning", output_key="process_route", skill="process_route_planning"),
            WorkflowStep("trial_need_assessment", "trial_need_assessment", output_key="trial_assessment", skill="trial_need_assessment"),
            WorkflowStep("trial_strategy_selection", "trial_strategy_selection", output_key="trial_selection", skill="trial_strategy_selection"),
            WorkflowStep("toolpath_strategy_selection", "toolpath_strategy_selection", output_key="toolpath_strategy", skill="toolpath_strategy_selection"),
            WorkflowStep("measurement_plan_generation", "measurement_plan_generation", output_key="measurement_plan", skill="measurement_plan_generation"),
            WorkflowStep("report_generation", "report_generation", output_key="task_report", skill="report_generation"),
        ),
    )


def microhole_array_task_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        "microhole_array_task_workflow",
        (
            WorkflowStep("task_intake", "task_intake", output_key="task_spec", skill="task_intake"),
            WorkflowStep("equipment_context_loading", "equipment_context_loading", output_key="equipment_snapshot", skill="equipment_context_loading", parallel_group="microhole_context"),
            WorkflowStep("load_domain_pack", "load_domain_pack", output_key="domain_pack", skill="geometry_interpretation", parallel_group="microhole_context"),
            WorkflowStep("aspect_ratio_assessment", "domain_geometry_check", output_key="domain_geometry_check", skill="geometry_interpretation"),
            WorkflowStep("density_and_pitch_check", "density_and_pitch_check", output_key="density_pitch_check", skill="constraint_extraction"),
            WorkflowStep("rag_evidence_retrieval", "rag_evidence_retrieval", output_key="evidence_pack", skill="rag_evidence_retrieval"),
            WorkflowStep("trial_strategy_selection", "trial_strategy_selection", output_key="trial_selection", skill="trial_strategy_selection"),
            WorkflowStep("monitoring_plan_generation", "in_process_monitoring_plan", output_key="monitoring_plan", skill="in_process_monitoring_plan"),
            WorkflowStep("bo_recommendation", "bo_recommendation", output_key="bo_recommendation", skill="bo_recommendation"),
            WorkflowStep("quality_plan_generation", "quality_plan_generation", output_key="quality_plan", skill="quality_plan_generation"),
        ),
    )


WORKFLOWS = {
    "complex_process_task": complex_process_task,
    "optical_component_task_workflow": optical_component_task_workflow,
    "microhole_array_task_workflow": microhole_array_task_workflow,
}


def get_workflow(name: str) -> WorkflowDefinition:
    try:
        return WORKFLOWS[name]()
    except KeyError as exc:
        raise ValueError(f"workflow not found: {name}") from exc
