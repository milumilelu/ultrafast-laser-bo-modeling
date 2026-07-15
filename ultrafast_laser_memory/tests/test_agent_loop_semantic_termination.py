from __future__ import annotations

import json
from threading import Event

from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat, handle_chat_stream_ndjson
from ultrafast_memory.db.init_db import init_database


def _session() -> str:
    return TestClient(app).post("/chat/sessions", json={}).json()["session_id"]


def test_rectangular_groove_commits_all_facts_once_then_asks_depth(isolated_root) -> None:
    init_database()

    response = handle_chat(ChatRequest(message="在铝基碳化硅板材上加工5*5mm的矩形槽"))

    assert response.current_stage_code == "ask_user"
    assert "目标深度" in response.assistant_message
    assert 3 <= response.assistant_message.count("？") <= 5
    spec = response.workflow_state["task_spec"]
    assert spec["material"] == {"name": "铝基碳化硅板材"}
    assert spec["process_intent"] == "groove_machining"
    assert spec["geometry"] == {
        "feature_type": "rectangular_groove",
        "dimensions": {"length_mm": 5.0, "width_mm": 5.0},
        "description": "5×5 mm 矩形槽",
    }
    assert response.workflow_state["missing_slots"] == ["geometry.depth_mm"]
    assert response.tool_calls == []
    assert response.workflow_state["runtime_metrics"] == {
        "decision_count": 1,
        "tool_call_count": 0,
    }

    completed = handle_chat(ChatRequest(session_id=response.session_id, message="1mm"))
    assert completed.current_stage_code == "final_answer"
    assert completed.workflow_state["task_spec"]["geometry"]["depth_mm"] == 1.0
    assert completed.workflow_state["missing_slots"] == []
    assert completed.tool_calls == []


def test_agent_can_finish_after_more_than_eight_decisions(isolated_root) -> None:
    init_database()

    class TenDecisionLLM:
        provider = "test"
        model = "ten-decisions"

        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls <= 9:
                content = {
                    "action": "call_tool",
                    "decision_summary": f"read equipment {self.calls}",
                    "tool_name": "get_equipment_context",
                    "arguments": {"observation_id": self.calls},
                }
            else:
                content = {
                    "action": "final_answer",
                    "decision_summary": "complete",
                    "message": "done",
                }
            return {"provider": self.provider, "model": self.model, "content": json.dumps(content)}

    result = run_main_agent_turn(
        session_id=_session(),
        message="execute a long bounded diagnostic",
        message_id="long-loop",
        client=TenDecisionLLM(),
    )

    assert result["content"] == "done"
    assert result["workflow_state"]["runtime_metrics"]["decision_count"] == 10
    assert len(result["tool_calls"]) == 9


def test_stream_publishes_live_status_and_heartbeat_while_llm_is_blocked(
    isolated_root, monkeypatch,
) -> None:
    init_database()
    release = Event()

    class BlockingLLM:
        provider = "test"
        model = "blocking"

        def chat(self, messages, **kwargs):
            assert release.wait(timeout=5)
            return {
                "provider": self.provider,
                "model": self.model,
                "content": json.dumps({
                    "action": "final_answer",
                    "decision_summary": "complete",
                    "message": "done",
                }),
            }

    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: BlockingLLM())
    monkeypatch.setattr("ultrafast_memory.chat.service.STREAM_HEARTBEAT_SECONDS", 0.01)
    stream = handle_chat_stream_ndjson(ChatRequest(message="分析这个普通任务", stream=True))

    assert next(stream)["type"] == "meta"
    assert next(stream)["type"] == "progress"
    live_events = []
    for _ in range(200):
        live_events.append(next(stream))
        if (
            sum(item["type"] == "thinking_status" for item in live_events) >= 2
            and any(
                item["type"] == "heartbeat" and item["wait_kind"] == "model"
                for item in live_events
            )
        ):
            break
    assert sum(item["type"] == "thinking_status" for item in live_events) >= 2
    heartbeat = next(
        item for item in live_events
        if item["type"] == "heartbeat" and item["wait_kind"] == "model"
    )
    assert heartbeat["elapsed_s"] >= 0
    assert heartbeat["wait_kind"] == "model"
    assert heartbeat["wait_name"] == "test/blocking"
    assert heartbeat["wait_component"] == "main_agent_planner"
    assert heartbeat["summary"] == "等待模型 test/blocking（主 Agent 规划，第 1 次调用）返回。"
    release.set()
    assert any(item["type"] == "delta" and item["content"] == "done" for item in stream)


def test_stream_heartbeat_names_the_blocking_router_model(isolated_root, monkeypatch) -> None:
    init_database()
    release = Event()

    class BlockingRouterLLM:
        provider = "test-router"
        model = "route-model"

        def chat(self, messages, **kwargs):
            assert release.wait(timeout=5)
            return {
                "provider": self.provider,
                "model": self.model,
                "content": json.dumps({
                    "primary_skill": "task_understanding",
                    "secondary_skills": [],
                    "intent": "skill_hint",
                    "workflow_stage": "agent_planning",
                    "confidence": 0.6,
                    "reason": "route complete",
                }),
            }

    class AnswerLLM:
        provider = "test"
        model = "answer"

        def chat(self, messages, **kwargs):
            return {
                "provider": self.provider,
                "model": self.model,
                "content": json.dumps({
                    "action": "final_answer",
                    "decision_summary": "complete",
                    "message": "done",
                }),
            }

    monkeypatch.setattr(
        "ultrafast_memory.chat.router.llm_router.create_llm_client",
        lambda config: BlockingRouterLLM(),
    )
    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: AnswerLLM())
    monkeypatch.setattr("ultrafast_memory.chat.service.STREAM_HEARTBEAT_SECONDS", 0.01)
    stream = handle_chat_stream_ndjson(ChatRequest(message="分析这个普通任务", stream=True))

    assert next(stream)["type"] == "meta"
    assert next(stream)["type"] == "progress"
    heartbeat = None
    for _ in range(300):
        item = next(stream)
        if item["type"] == "heartbeat" and item["wait_kind"] == "model":
            heartbeat = item
            break

    assert heartbeat is not None
    assert heartbeat["wait_name"] == "test-router/route-model"
    assert heartbeat["wait_component"] == "llm_router"
    assert heartbeat["summary"] == (
        "等待模型 test-router/route-model（Skill 路由，第 1 次调用）返回。"
    )
    release.set()
    assert any(item["type"] == "delta" and item["content"] == "done" for item in stream)


def test_stream_heartbeat_names_the_blocking_tool(isolated_root, monkeypatch) -> None:
    init_database()
    release = Event()

    class ToolThenAnswerLLM:
        provider = "test"
        model = "tool-planner"

        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = {
                    "action": "call_tool",
                    "decision_summary": "read equipment",
                    "tool_name": "get_equipment_context",
                    "arguments": {},
                }
            else:
                content = {
                    "action": "final_answer",
                    "decision_summary": "complete",
                    "message": "done",
                }
            return {"provider": self.provider, "model": self.model, "content": json.dumps(content)}

    class BlockingExecution:
        def to_tool_result(self, tool_name):
            return {
                "tool_name": tool_name,
                "status": "success",
                "summary": "equipment loaded",
                "data": {},
            }

    class BlockingToolExecutor:
        def __init__(self, registry) -> None:
            self.registry = registry

        def execute(self, tool_name, arguments, context):
            assert tool_name == "get_equipment_context"
            assert release.wait(timeout=5)
            return BlockingExecution()

    llm = ToolThenAnswerLLM()
    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: llm)
    monkeypatch.setattr(
        "ultrafast_memory.agent_runtime.main_agent_loop.ToolExecutor",
        BlockingToolExecutor,
    )
    monkeypatch.setattr("ultrafast_memory.chat.service.STREAM_HEARTBEAT_SECONDS", 0.01)
    stream = handle_chat_stream_ndjson(ChatRequest(message="分析并读取设备边界", stream=True))

    assert next(stream)["type"] == "meta"
    assert next(stream)["type"] == "progress"
    heartbeat = None
    for _ in range(300):
        item = next(stream)
        if item["type"] == "heartbeat" and item["wait_kind"] == "tool":
            heartbeat = item
            break

    assert heartbeat is not None
    assert heartbeat["wait_name"] == "get_equipment_context"
    assert heartbeat["summary"].startswith("等待工具 get_equipment_context 返回：")
    release.set()
    assert any(item["type"] == "delta" and item["content"] == "done" for item in stream)
