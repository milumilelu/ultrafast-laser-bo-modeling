from __future__ import annotations

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_bootstrap.candidate_builder import build_knowledge_candidate
from ultrafast_memory.knowledge_bootstrap.source_registry import register_external_source
from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.review_queue import create_review_task
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def _review_parameter_candidate(action: str, *, laser_power_w: float = 2.1) -> None:
    source = register_external_source({
        "title": "Reviewed alumina laser parameter study",
        "url": "https://example.org/reviewed-alumina-study",
        "snippet": "Reviewed structured parameter evidence.",
        "source_type": "paper",
        "provider": "test",
    })
    candidate = build_knowledge_candidate(source, {
        "claim": "Alumina surface texturing used reviewed laser power and frequency settings.",
        "material": "alumina",
        "process_type": "surface_texturing",
        "parameter": {
            "laser_power_W": {"value": laser_power_w, "unit": "W"},
            "frequency_kHz": {"lower": 80, "upper": 120, "unit": "kHz"},
        },
        "condition": {"atmosphere": "air"},
        "usable_for": ["literature_background", "parameter_recommendation"],
        "not_usable_for": ["formal_process", "BO_training"],
        "evidence_type": "paper",
        "confidence": 0.9,
    })
    review = create_review_task(
        candidate["candidate_id"],
        candidate["risk_level"],
        candidate["suggested_action"],
    )
    apply_review_action(
        review["review_id"],
        ReviewActionRequest(action=action, reviewer_id="expert"),
    )


def _payload() -> dict:
    return {
        "task_context": {
            "material": {"name": "alumina"},
            "process_intent": "surface_texturing",
        },
        "process_plan": {
            "objective": "texture alumina",
            "controllable_variables": [
                {"name": "laser_power_W", "role": "process_setpoint"},
                {"name": "frequency_kHz", "role": "process_setpoint"},
            ],
        },
        "variables": ["laser_power_W", "frequency_kHz"],
        "equipment_context": {
            "fixed_conditions": {"wavelength_nm": 1030},
            "tunable_capabilities": {
                "laser_power_W": {"min": 0.1, "max": 5.0, "unit": "W"},
                "frequency_kHz": {"min": 2, "max": 200, "unit": "kHz"},
            },
        },
        "parameters": {"laser_power_W": 4.9, "frequency_kHz": 199},
    }


def test_rag_parameter_recommendation_extracts_reviewed_values_with_per_parameter_refs(
    isolated_root,
) -> None:
    init_database()
    _review_parameter_candidate("accept_as_literature_evidence")

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "recommend_parameters_rag", _payload(), {"session_id": "rag-parameter"},
    ).output

    assert result["status"] == "success"
    assert result["process_parameters"]["laser_power_W"]["value"] == 2.1
    assert result["process_parameters"]["frequency_kHz"]["value"] == 100.0
    assert result["process_parameters"]["laser_power_W"]["source_type"] == "reviewed_rag"
    assert result["process_parameters"]["laser_power_W"]["source_refs"]
    assert result["process_parameters"]["laser_power_W"]["authority_level"] == "literature_prior"
    assert result["process_parameters"]["laser_power_W"]["allowed_for_trial"] is True
    assert result["process_parameters"]["laser_power_W"]["allowed_for_formal_process"] is False
    assert result["process_parameters"]["laser_power_W"]["value"] != 4.9


def test_background_level_evidence_cannot_generate_parameter_candidate(isolated_root) -> None:
    init_database()
    _review_parameter_candidate("accept_to_rag")

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "recommend_parameters_rag", _payload(), {"session_id": "rag-parameter"},
    ).output

    assert result["status"] == "insufficient_data"
    assert result["process_parameters"] == {}
    assert set(result["missing_variables"]) == {"laser_power_W", "frequency_kHz"}


def test_out_of_bounds_evidence_is_rejected_instead_of_clipped_to_machine_limit(
    isolated_root,
) -> None:
    init_database()
    _review_parameter_candidate("accept_as_literature_evidence", laser_power_w=20.0)

    result = ToolExecutor(build_main_agent_tool_registry()).execute(
        "recommend_parameters_rag", _payload(), {"session_id": "rag-out-of-bounds"},
    ).output

    assert result["status"] == "insufficient_data"
    assert result["process_parameters"] == {}
    assert "laser_power_W" in result["missing_variables"]
    extraction = result["data_support"]["extraction"]
    assert extraction["parameter_details"]["laser_power_W"]["uncertainty"][
        "rejection_reason"
    ] == "outside_equipment_bounds"
