from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.equipment.bounds import build_machine_bounds


def _session() -> str:
    return TestClient(app).post("/chat/sessions", json={}).json()["session_id"]


def test_context_persistence_failure_warns_but_question_continues(isolated_root, monkeypatch):
    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.working_context.ContextPersistenceService.persist",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    result = run_main_agent_turn(
        session_id=_session(), message="在铝基碳化硅板材上加工5*5mm的矩形槽",
        message_id="persistence", client=None,
    )
    assert result["final_action"]["action"] == "ask_user"
    assert "目标深度" in result["content"]
    assert any("持久化失败" in warning for warning in result["warnings"])


def test_result_postprocess_failure_does_not_block_final_answer(isolated_root, monkeypatch):
    class ResultLLM:
        provider = "test"
        model = "result"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            action = ({"action": "call_tool", "decision_summary": "记录结果",
                       "tool_name": "record_process_result", "arguments": {"measurements": {"kerf_mm": 0.2}}}
                      if self.calls == 1 else
                      {"action": "final_answer", "decision_summary": "结果已分析", "message": "结果已记录，可继续。"})
            return {"content": json.dumps(action, ensure_ascii=False)}

    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.main_agent_loop._run_result_postprocess_hooks",
        lambda *args: (_ for _ in ()).throw(RuntimeError("candidate failed")),
    )
    result = run_main_agent_turn(session_id=_session(), message="加工完成，结果不错",
                                 message_id="post", client=ResultLLM())
    assert result["content"] == "结果已记录，可继续。"
    assert any("后处理失败" in warning for warning in result["warnings"])


def test_repeated_tool_observation_is_reused_then_loop_is_stopped(isolated_root):
    class RepeatingLLM:
        provider = "test"
        model = "repeat"

        def chat(self, messages, **kwargs):
            return {"content": json.dumps({"action": "call_tool", "decision_summary": "重复读取",
                                            "tool_name": "get_equipment_context", "arguments": {}})}

    result = run_main_agent_turn(session_id=_session(), message="读取设备", message_id="repeat", client=RepeatingLLM())
    assert result["final_action"]["action"] == "ask_user"
    assert len(result["tool_calls"]) == 1
    assert any(event["event_type"] == "tool_cache_hit" for event in result["events"])
    assert any(event["event_type"] == "probable_agent_loop" for event in result["events"])


def test_trial_evaluation_needs_no_approval(isolated_root, monkeypatch):
    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.tool_registry.TrialApplicationService.evaluate",
        lambda self, result_id, payload: {"result_id": result_id, "decision": "pass"},
    )
    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "manage_trial", {"operation": "evaluate", "result_id": "r1"},
        {"session_id": "s", "working_context": {"task": {}}, "human_approved": False},
    )
    assert execution.status == "succeeded"
    assert execution.output["result"]["decision"] == "pass"


def test_trial_budget_and_bo_eligibility_do_not_stop_foreground(isolated_root):
    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "record_process_result", {"measurements": {"depth_um": 20}, "iteration": 6},
        {"session_id": _session(), "working_context": {"task": {}}},
    )
    assert execution.status == "succeeded"
    assert execution.output["bo_data_eligibility"]["eligible"] is False
    assert execution.output["status"] == "success"


def test_formal_process_checkpoint_and_incomplete_measurement(isolated_root):
    executor = ToolExecutor(build_main_agent_tool_registry())
    context = {"session_id": _session(), "working_context": {"task": {}},
               "equipment_snapshot": build_machine_bounds(), "human_approved": False}
    prepared = executor.execute("manage_process", {"operation": "prepare", "parameters": {"power": 2}}, context)
    plan_id = prepared.output["result"]["plan_id"]
    blocked = executor.execute("manage_process", {"operation": "start", "plan_id": plan_id}, context)
    assert blocked.output["status"] == "blocked"
    started = executor.execute("manage_process", {"operation": "start", "plan_id": plan_id},
                               {**context, "human_approved": True})
    execution_id = started.output["result"]["execution_id"]
    checkpoint = executor.execute("manage_process", {
        "operation": "record_checkpoint", "execution_id": execution_id,
        "progress_percent": 30, "observation": {"edge_chipping": "increasing"},
    }, context)
    assert checkpoint.output["status"] == "success"
    assert checkpoint.output["result"]["decision"] == "agent_review_required"
    result = executor.execute("manage_process", {
        "operation": "record_result", "execution_id": execution_id,
        "required_metrics": ["edge_chipping_um", "depth_um"], "measurements": {"depth_um": 50},
    }, context)
    assert result.status == "insufficient_data"
    assert result.output["result"]["quality"]["decision"] == "INCOMPLETE_DATA"


def test_explicit_real_action_approval_is_scoped_to_start(isolated_root):
    executor = ToolExecutor(build_main_agent_tool_registry())
    session_id = _session()
    context = {"session_id": session_id, "working_context": {"task": {}},
               "equipment_snapshot": build_machine_bounds(), "human_approved": False}
    prepared = executor.execute("manage_process", {"operation": "prepare"}, context)
    plan_id = prepared.output["result"]["plan_id"]

    class StartLLM:
        provider = "test"
        model = "start"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            action = ({"action": "call_tool", "decision_summary": "开始正式加工", "tool_name": "manage_process",
                       "arguments": {"operation": "start", "plan_id": plan_id}}
                      if self.calls == 1 else
                      {"action": "final_answer", "decision_summary": "已开始", "message": "正式加工已开始。"})
            return {"content": json.dumps(action, ensure_ascii=False)}

    result = run_main_agent_turn(session_id=session_id, message="确认开始正式加工",
                                 message_id="approve", client=StartLLM())
    assert result["tool_calls"][0]["result"]["status"] == "success"
    approvals = [item for item in result["working_context"]["observations"]
                 if item.get("type") == "UserApprovalObservation"]
    assert approvals[-1]["scope"] == {"tool": "manage_process", "operation": "start"}
    assert approvals[-1]["one_time"] is True
