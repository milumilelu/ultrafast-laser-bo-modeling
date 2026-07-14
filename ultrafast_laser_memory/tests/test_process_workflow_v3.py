from __future__ import annotations

import pytest

from ultrafast_memory.process_workflow.campaign import CampaignService
from ultrafast_memory.process_workflow.policy import ParameterRecommendationPolicy, formal_release_gate
from ultrafast_memory.process_workflow.schemas import (
    NextAction, ParameterRecommendation, ParameterValue, ProcessState,
)
from ultrafast_memory.process_workflow.state_machine import ProcessStateMachine
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.chat.workflow_status import record_public_trace
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_agent.skills import get_default_skill_registry


def rec(mode, support, intended="simple_trial", source="bo_recommendation"):
    return ParameterRecommendation(
        recommendation_id=f"{mode}-{support}", recommendation_mode=mode,
        support_status=support, authority_level="verified" if mode == "bo" else "evidence_based",
        intended_use=intended,
        parameters=[ParameterValue(name="power", value=2, unit="W", source_type=source,
            allowed_for_simple_trial=True, allowed_for_full_trial=mode == "bo",
            allowed_for_formal_process=mode == "bo", allowed_for_bo_prior=mode != "llm_fallback")],
    )


def test_parameter_policy_is_bo_first_and_fallback_is_simple_only():
    calls = []
    def bo(ctx):
        calls.append("bo")
        return rec("bo", "insufficient")
    def rag(ctx):
        calls.append("rag")
        return rec("rag", "insufficient", ctx["intended_use"], "rag_parameter_recommendation")
    def llm(ctx):
        calls.append("llm")
        return rec("llm_fallback", "supported", source="anything")
    policy = ParameterRecommendationPolicy(bo, rag, llm)
    result = policy.recommend({"allow_llm_fallback": True, "user_allows_exploration": True,
        "trial_allowed": True, "equipment_hard_bounds_complete": True})
    assert calls == ["bo", "rag", "llm"]
    assert result.intended_use == "simple_trial"
    assert result.parameters[0].source_type == "llm_fallback_hypothesis"
    assert not result.parameters[0].allowed_for_formal_process


def test_process_state_machine_blocks_shortcuts_and_progress_is_real():
    sm = ProcessStateMachine()
    with pytest.raises(ValueError):
        sm.transition(ProcessState.FORMAL_PROCESS_READY)
    sm.transition(ProcessState.INTAKE)
    progress = sm.progress(NextAction(action_type="submit", title="补充字段"))
    assert progress.percent == round(progress.completed_steps / progress.total_steps * 100)
    assert progress.current_stage == "INTAKE"


def test_campaign_requires_valid_observation_before_snapshot_and_separates_fidelity(isolated_root):
    service = CampaignService()
    campaign = service.create(campaign_id="c1", task_id="t1", campaign_type="simple_trial_campaign",
        fidelity_level="simple_trial", material_context={"material": "CFRP"}, equipment_revision="r1",
        active_variables=["power"], objectives=[{"name": "depth"}], hard_constraints=[{"name": "delamination"}],
        search_space={"power": [1, 3]}, budget={"max_iterations": 3})
    with pytest.raises(ValueError):
        service.update_model("c1")
    observation = service.ingest_observation("c1", {"parameters": {"power": 2}, "units": {"power": "W"},
        "equipment_revision": "r1", "material_batch": "b1", "measurements": {"depth": 10}, "attachments": ["trace.csv"]})
    assert observation["bo_eligible"]
    assert service.update_model("c1")["training_sample_ids"] == [observation["observation_id"]]
    assert campaign.fidelity_level == "simple_trial"
    assert service.bo_mode(9) == "rule_based_cold_start"
    assert service.bo_mode(10) == "hybrid_rule_bo"
    assert service.bo_mode(30) == "data_driven_bo"
    service.create_iteration("c1", {"effective_sample_count": 1}, [{"power": 2}])
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM optimization_campaign").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM optimization_iteration").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM optimization_candidate").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM model_snapshot").fetchone()[0] == 1


def test_public_reasoning_summary_is_persisted_without_hidden_reasoning(isolated_root):
    record_public_trace("s1", "decision_rationale", "参数来源选择", "BO 不足，转入 RAG。",
                        workflow_id="run-1", detail={"chain_of_thought": "must not persist"})
    with get_connection() as connection:
        row = connection.execute(
            "SELECT summary, data_json FROM runtime_public_event WHERE session_id = 's1'"
        ).fetchone()
        legacy_count = connection.execute("SELECT COUNT(*) FROM public_reasoning_trace").fetchone()[0]
    assert "chain_of_thought" not in row[1]
    assert "BO 不足" in row[0]
    assert legacy_count == 0


def test_v3_skills_are_registered_and_trace_off_is_enforced(isolated_root):
    names = {item.name for item in get_default_skill_registry().list()}
    assert {"parameter_recommendation_planning", "optimization_campaign_initialization",
            "observation_validation", "formal_local_adjustment", "campaign_termination"} <= names
    session = handle_chat(ChatRequest(message="/trace off"))
    response = handle_chat(ChatRequest(session_id=session.session_id, message="普通咨询"))
    assert response.execution_trace == []
    assert response.reasoning_trace == []


def test_formal_release_requires_trial_provenance_revision_and_preflight():
    allowed, reasons = formal_release_gate(trial_passed=False, source_types=["rag_parameter_recommendation"],
        equipment_revision_matches=False, preflight_complete=False)
    assert not allowed
    assert set(reasons) == {"trial_not_passed", "illegal_parameter_source", "equipment_revision_changed", "preflight_incomplete"}
