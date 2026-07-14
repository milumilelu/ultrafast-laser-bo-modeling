from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.chat.router.hybrid_router import route_message
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.agent_runtime.planner import MainAgentPlanner
from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_agent.runtime import ToolExecutor


class DrillingAgentLLM:
    provider = "test"
    model = "drilling-regression"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls)
        if index == 1:
            # Real compatible providers occasionally omit schema-required keys.
            return {"content": '{"action":"call_tool","tool_name":"update_task_context"}'}
        if index == 2:
            return {"content": json.dumps({
                "action": "call_tool",
                "decision_summary": "提取用户明确提供的通孔任务事实。",
                "tool_name": "update_task_context",
                "arguments": {"updates": [
                    {"field_name": "material", "value": "金刚石", "evidence": "金刚石"},
                    {"field_name": "thickness_mm", "value": 4, "unit": "mm", "evidence": "4mm"},
                    {"field_name": "process_type", "value": "通孔", "evidence": "通孔"},
                    {"field_name": "hole_diameter_mm", "value": 2, "unit": "mm", "evidence": "直径2mm"},
                    {"field_name": "through_hole", "value": True, "evidence": "通孔"},
                ]},
                "message": None,
            }, ensure_ascii=False)}
        return {"content": json.dumps({
            "action": "final_answer",
            "decision_summary": "任务事实已保存，可按需继续检索证据。",
            "tool_name": None,
            "arguments": {},
            "message": "已记录金刚石通孔任务，可继续查询文献或历史案例。",
        }, ensure_ascii=False)}


def test_diamond_through_hole_survives_provider_compatible_partial_action(isolated_root) -> None:
    client = TestClient(app)
    session_id = client.post("/chat/sessions", json={}).json()["session_id"]
    llm = DrillingAgentLLM()

    result = run_main_agent_turn(
        session_id=session_id,
        message="在4mm厚的金刚石上加工一个直径2mm的通孔",
        message_id="msg-drilling-regression",
        client=llm,
        active_skills=["task_understanding", "process_planning"],
    )

    spec = result["task_spec"]
    assert spec["material"] == "diamond"
    assert spec["thickness_mm"] == 4
    assert spec["process_type"] == "hole_drilling"
    assert spec["hole_diameter_mm"] == 2
    assert spec["through_hole"] is True
    assert "cut_length_mm" not in spec
    assert spec["geometry"]["hole_diameter_mm"] == 2
    assert spec["geometry"]["through_hole"] is True
    assert result["tool_calls"][0]["tool_name"] == "update_task_context"
    assert llm.calls[0]["response_format"] == {"type": "json_object"}
    assert "材料" not in result["content"]
    assert "厚度" not in result["content"]
    assert "切割长度" not in result["content"]

    persisted = get_session_state(session_id)["collected_slots"]["task_spec"]
    assert persisted == spec


def test_machining_rule_is_only_a_soft_candidate(isolated_root, monkeypatch) -> None:
    monkeypatch.delenv("ULTRAFAST_LLM_PROVIDER", raising=False)
    plan = route_message(
        "在4mm厚的金刚石上加工一个直径2mm的通孔",
        "soft-route-session",
        "soft-route-message",
    )
    assert plan.primary_skill == "task_understanding"
    assert plan.confidence < 0.9
    assert plan.route_source != "mandatory_process_rule"
    assert "state_update" not in plan.model_dump()


def test_controller_can_select_any_registered_tool() -> None:
    class SearchLLM:
        provider = "test"
        model = "search"

        def chat(self, messages, **kwargs):
            return {"content": json.dumps({
                "action": "call_tool",
                "decision_summary": "已有检索所需上下文。",
                "tool_name": "search_knowledge",
                "arguments": {"query": "diamond hole drilling"},
                "message": None,
            })}

    registry = build_main_agent_tool_registry()
    action = MainAgentPlanner(SearchLLM()).decide(
        message="查一下证据",
        task_spec={"material": "diamond", "process_type": "hole_drilling"},
        business_state="INTAKE",
        context=ClarificationContext(workflow_type="task_understanding", stage="INTAKE"),
        available_tools=registry.schemas_for_agent(),
    )
    assert action.tool_name == "search_knowledge"


def test_tool_reports_action_scoped_missing_context() -> None:
    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "recommend_parameters_bo",
        {},
        {"task_spec": {"material": "diamond", "process_type": "hole_drilling"}},
    )
    assert execution.status == "insufficient_data"
    assert execution.output["missing"] == [
        "task_spec.objective",
        "equipment_snapshot.machine_bounds",
    ]
