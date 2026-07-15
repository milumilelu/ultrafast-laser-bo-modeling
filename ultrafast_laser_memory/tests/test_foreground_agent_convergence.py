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
    assert result["final_action"]["action"] == "final_answer"
    assert len(result["tool_calls"]) == 1
    assert any(event["event_type"] == "tool_cache_hit" for event in result["events"])
    assert any(event["event_type"] == "probable_agent_loop" for event in result["events"])


def test_existing_context_reuse(isolated_root, monkeypatch):
    from ultrafast_memory.agent_runtime import tool_registry as tool_module

    calls = 0
    original = tool_module._equipment

    def counted_equipment(payload, context):
        nonlocal calls
        calls += 1
        return original(payload, context)

    class ReadThenAnswerLLM:
        provider = "test"
        model = "cache"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            action = (
                {"action": "call_tool", "decision_summary": "读取设备",
                 "tool_name": "get_equipment_context", "arguments": {}}
                if self.calls == 1 else
                {"action": "final_answer", "decision_summary": "完成", "message": "设备上下文可用。"}
            )
            return {"content": json.dumps(action, ensure_ascii=False)}

    monkeypatch.setattr(tool_module, "_equipment", counted_equipment)
    session_id = _session()
    first = run_main_agent_turn(
        session_id=session_id, message="读取设备", message_id="cache-1", client=ReadThenAnswerLLM(),
    )
    second = run_main_agent_turn(
        session_id=session_id, message="再次读取设备", message_id="cache-2", client=ReadThenAnswerLLM(),
    )

    assert len(first["tool_calls"]) == 1
    assert second["tool_calls"] == []
    assert calls == 1
    assert any(event["event_type"] == "tool_cache_hit" for event in second["events"])


def test_background_failure_does_not_block(isolated_root, monkeypatch):
    class ResultThenAnswerLLM:
        provider = "test"
        model = "sidecar-failure"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            action = (
                {"action": "call_tool", "decision_summary": "记录测量",
                 "tool_name": "record_process_result",
                 "arguments": {"measurements": {"quality": "pass"}}}
                if self.calls == 1 else
                {"action": "final_answer", "decision_summary": "结果已分析", "message": "前台结果正常返回。"}
            )
            return {"content": json.dumps(action, ensure_ascii=False)}

    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.working_context.ContextPersistenceService.persist",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("persistence failed")),
    )
    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.main_agent_loop._run_result_postprocess_hooks",
        lambda *args: (_ for _ in ()).throw(RuntimeError("candidate/report sidecar failed")),
    )

    result = run_main_agent_turn(
        session_id=_session(), message="记录当前测量并给出结论",
        message_id="sidecar", client=ResultThenAnswerLLM(),
    )

    assert result["content"] == "前台结果正常返回。"
    assert result["final_action"]["action"] == "final_answer"
    assert any("持久化失败" in warning for warning in result["warnings"])
    assert any("后处理失败" in warning for warning in result["warnings"])


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


def test_cfrp_regression_uses_one_runtime_and_composite_parameter_policy(isolated_root):
    class IntakeLLM:
        provider = "test"
        model = "intake"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            return {"content": json.dumps({
                "action": "ask_user",
                "decision_summary": "只补充影响当前路线的信息",
                "message": "目标切割轮廓和长度是多少？",
            }, ensure_ascii=False)}

    class PlanningLLM:
        provider = "test"
        model = "planning"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                action = {
                    "action": "call_tool", "decision_summary": "读取设备事实",
                    "tool_name": "get_equipment_context", "arguments": {},
                }
            elif self.calls == 2:
                action = {
                    "action": "call_tool", "decision_summary": "按统一策略推荐参数",
                    "tool_name": "recommend_process_parameters",
                    "arguments": {
                        "task_context": {
                            "material": {"name": "CFRP", "grade": "T300"},
                            "process_intent": "cutting",
                        },
                        "process_plan": {
                            "objective": "无分层切割试切",
                            "controllable_variables": [
                                {"name": "laser_power_W", "role": "process_setpoint"},
                            ],
                        },
                        "variables": ["laser_power_W"],
                        "equipment_context": build_machine_bounds(),
                    },
                }
            else:
                action = {
                    "action": "ask_user", "decision_summary": "参数来源已检查",
                    "message": "当前证据只支持试切；请选择简化试切还是完整试切？",
                }
            return {"content": json.dumps(action, ensure_ascii=False)}

    session_id = _session()
    intake_llm = IntakeLLM()
    first = run_main_agent_turn(
        session_id=session_id,
        message="我想切割 5 mm 厚的碳纤维板，板号 T300。",
        message_id="cfrp-1",
        client=intake_llm,
    )
    assert first["final_action"]["action"] == "ask_user"
    assert first["task_spec"]["material"]["grade"] == "T300"
    assert first["task_spec"]["workpiece"]["thickness_mm"] == 5
    assert first["workflow_state"]["runtime_metrics"]["model_call_count"] == 1

    planning_llm = PlanningLLM()
    second = run_main_agent_turn(
        session_id=session_id,
        message="只要求无分层，使用压缩空气，允许层切，无效率要求。",
        message_id="cfrp-2",
        client=planning_llm,
    )
    assert second["task_spec"]["quality_requirement"] == "no_delamination"
    assert second["task_spec"]["auxiliary"] == "compressed_air"
    assert second["task_spec"]["layer_cut_allowed"] is True
    assert [item["tool_name"] for item in second["tool_calls"]] == [
        "get_equipment_context", "recommend_process_parameters",
    ]
    policy_result = second["tool_calls"][1]["result"]["data"]
    assert [item["step"] for item in policy_result["internal_trace"]][:2] == [
        "bo_parameter_recommendation", "rag_parameter_recommendation",
    ]
    assert second["final_action"]["action"] == "ask_user"
    assert second["workflow_state"]["runtime_metrics"]["model_call_count"] == 3


def test_rule_based_bo_cannot_unlock_formal_process(isolated_root, monkeypatch):
    from ultrafast_memory.agent_runtime import tool_registry as tool_module

    class ColdStartAdapter:
        def recommend(self, *args, **kwargs):
            return {
                "model_status": "rule_based_cold_start",
                "sample_count": 0,
                "recommended_parameters": {"laser_power_W": 1.0},
                "bo_invoked": False,
                "readiness_report": {
                    "complete_feature_count": 0,
                    "validation_metrics": {},
                    "uncertainty_calibrated": False,
                },
            }

    monkeypatch.setattr(tool_module, "LegacyBOCompatibilityAdapter", ColdStartAdapter)
    result = tool_module._recommend_bo(
        {"variables": ["laser_power_W"]},
        {
            "task_spec": {"material": "CFRP", "process_type": "cutting"},
            "equipment_snapshot": {
                "fixed_conditions": {},
                "tunable_capabilities": {
                    "laser_power_W": {"min": 0.1, "max": 5.0, "unit": "W"},
                },
            },
        },
    )
    assert result["status"] == "partial_support"
    assert result["data_support"]["model_mode"] == "rule_based_cold_start"
    assert result["allowed_for_trial"] is True
    assert result["allowed_for_formal_process"] is False
