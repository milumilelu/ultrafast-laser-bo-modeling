from __future__ import annotations

from pathlib import Path

from ultrafast_memory.chat.workflow_projection import WorkflowProjectionService
from ultrafast_memory.process_workflow.business_state import BusinessStateController


def test_process_projection_is_pure_and_uses_canonical_business_state():
    task = {
        "material": "CFRP", "process_type": "cutting", "thickness_mm": 3,
        "quality_requirement": "no_delamination", "cut_length_mm": 100,
        "efficiency_requirement": "none", "auxiliary": "compressed_air",
        "layer_cut_allowed": True,
    }
    projection = WorkflowProjectionService.build_process(
        task_spec=task,
        workflow_state={
            "business_state": "TRIAL", "substatus": "TRIAL_RESULT_PENDING",
            "state": "TRIAL_RESULT_PENDING",
        },
        recent_events=[{"step": "trial_plan_generation"}],
        next_action={"action_type": "submit_trial_result", "blocking": True},
    )

    assert projection.business_state == "TRIAL"
    assert projection.substatus == "TRIAL_RESULT_PENDING"
    assert projection.missing_fields == []
    assert projection.current_step == "trial_plan_generation"
    assert projection.next_action["action_type"] == "submit_trial_result"


def test_legacy_projection_accepts_structured_task_not_user_message():
    projection = WorkflowProjectionService.build_legacy(
        workflow_type="crl_task_planning",
        task_spec={"material": "diamond", "component_type": "CRL"},
        equipment_snapshot={"active": False},
        clarification_round=1,
    )

    assert projection.business_state == "INTAKE"
    assert projection.missing_fields == [
        "diamond_type", "post_processing_allowed", "laser_system",
    ]


def test_business_state_is_not_silently_overwritten_by_legacy_substatus():
    projection = WorkflowProjectionService.build_process(
        task_spec={},
        workflow_state={
            "business_state": "TRIAL", "substatus": "BO_RUNNING", "state": "BO_RUNNING",
        },
    )

    assert projection.business_state == "TRIAL"
    assert projection.substatus == "BO_RUNNING"


def test_business_state_controller_records_non_linear_projection_without_gating():
    workflow = BusinessStateController.ensure({"state": "INTAKE"})
    BusinessStateController.transition(workflow, "FORMAL_PROCESS_RUNNING")
    assert workflow["business_state"] == "WAITING_EXTERNAL_RESULT"
    assert workflow["state_projection_warning"] == (
        "non_linear_projection:INTAKE->WAITING_EXTERNAL_RESULT"
    )


def test_workflow_status_source_is_read_only_projection(project_root: Path):
    source = (project_root / "src/ultrafast_memory/chat/workflow_status.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "get_connection", "INSERT ", "record_agent_trace_event", "parse_process_task_fields",
        "legacy_non_process_status_snapshot", "build_machine_bounds", "TaskWorkflowService",
        "query_rag", "recommend_trial_parameters",
    )
    assert not any(token in source for token in forbidden)
