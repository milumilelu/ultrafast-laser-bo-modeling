from __future__ import annotations

import time
import sqlite3

import pytest

from ultrafast_agent.runtime import (
    RunContext,
    ToolContract,
    ToolRegistry,
    WorkflowDefinition,
    WorkflowRunner,
    WorkflowStep,
)
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.knowledge_use.service import KnowledgeUseApplicationService
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.hybrid_retriever import HybridRetriever
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks
from ultrafast_memory.rag.query_service import clear_rag_query_cache, query_rag
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.vector_store import SQLiteVectorStore
from ultrafast_memory.trial.service import TrialApplicationService
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat, handle_chat_stream_ndjson


EQUIPMENT = {
    "active": True,
    "revision_id": "eq-fault-1",
    "machine_bounds": {"laser_power_W": [1, 20]},
}
HIGH_RISK = {
    "intended_use": "parameter_recommendation",
    "task_spec": {"material": "glass", "process_type": "TGV_drilling"},
    "equipment": EQUIPMENT,
    "evidence": [
        {
            "evidence_id": "fault-evidence-1",
            "claim": "推荐激光功率为 10 W",
            "parameters": {"laser_power_W": 10},
        }
    ],
}


class UnavailableReviewRepository:
    def find_reusable_approval(self, approval_key, task_id):
        raise sqlite3.OperationalError("database is locked")


class NoApprovalRepository:
    def find_reusable_approval(self, approval_key, task_id):
        return None

    def find_task_decision(self, task_id):
        return None

    def create_decision(self, **kwargs):
        return {"decision_id": "decision-created", "status": "pending"}


def test_review_storage_outage_blocks_high_risk_use_but_not_background():
    service = KnowledgeUseApplicationService(UnavailableReviewRepository())

    blocked = service.evaluate("fault-task", HIGH_RISK)
    background = service.evaluate(
        "background-task",
        {**HIGH_RISK, "intended_use": "background_explanation"},
    )

    assert blocked["status"] == "blocked"
    assert blocked["reasons"] == ["review_service_unavailable"]
    assert blocked["fail_closed"] is True
    assert background["status"] == "allowed"


def test_client_supplied_approval_id_cannot_bypass_repository_validation():
    payload = {
        **HIGH_RISK,
        "evidence": [{**HIGH_RISK["evidence"][0], "approval_id": "forged-approval"}],
    }

    result = KnowledgeUseApplicationService(NoApprovalRepository()).evaluate(
        "forged-task", payload
    )

    assert result["status"] == "approval_required"
    assert result["decision_id"] == "decision-created"


def test_rag_retrieval_outage_returns_insufficient_degraded_pack(
    isolated_root, mixed_literature_root, monkeypatch
):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default", "embedding_dimension": 32})
    index_pending_chunks(index["index_id"])
    clear_rag_query_cache()

    def unavailable(*args, **kwargs):
        raise TimeoutError("injected retriever timeout")

    monkeypatch.setattr(HybridRetriever, "retrieve", unavailable)
    monkeypatch.setattr(SQLiteLexicalIndex, "search", unavailable)
    result = query_rag({"query": "TGV taper crack", "top_k": 4})

    assert result["evidence_status"] == "insufficient"
    assert result["hits"] == []
    assert result["retrieval_metadata"]["degraded"] is True
    assert result["retrieval_metadata"]["failure_stage"] == "retrieval"
    assert result["retrieval_metadata"]["error_type"] == "TimeoutError"


def test_corrupt_vector_index_falls_back_to_sqlite_lexical(
    isolated_root, mixed_literature_root, monkeypatch
):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default", "embedding_dimension": 32})
    index_pending_chunks(index["index_id"])
    clear_rag_query_cache()

    def corrupt_vector(*args, **kwargs):
        raise ValueError("injected corrupt vector payload")

    monkeypatch.setattr(SQLiteVectorStore, "query", corrupt_vector)
    result = query_rag({"query": "TGV taper crack", "top_k": 4})

    assert result["hits"]
    assert result["retrieval_metadata"]["degraded"] is True
    assert result["retrieval_metadata"]["fallback"] == "sqlite_lexical"
    assert result["retrieval_metadata"]["error_type"] == "ValueError"


def test_llm_tool_timeout_fails_workflow_closed():
    def slow_llm(payload, context):
        time.sleep(0.1)
        return {"content": "late"}

    registry = ToolRegistry()
    registry.register(
        ToolContract("llm_adapter", "Injected LLM adapter", slow_llm, timeout_ms=10)
    )
    workflow = WorkflowDefinition(
        "llm-timeout",
        (WorkflowStep("generate", "llm_adapter", output_key="answer"),),
    )

    result = WorkflowRunner(registry).run(workflow, RunContext({}))

    assert result.status == "failed"
    assert "WorkflowTimeout" in (result.error or "")
    assert "answer" not in result.data


def test_missing_trial_result_never_unlocks_formal_execution(isolated_root):
    init_database()

    with pytest.raises(ValueError, match="trial result not found"):
        TrialApplicationService().evaluate("missing-result", {})


class FailingLLM:
    provider = "injected"
    model = "injected-failure"

    def chat(self, messages, **kwargs):
        raise TimeoutError("injected LLM timeout")

    def stream_chat(self, messages, **kwargs):
        yield {"type": "error", "message": "injected provider detail"}
        yield {"type": "done"}


def test_llm_failure_becomes_safe_agent_action_for_sync_and_stream(
    isolated_root, monkeypatch
):
    init_database()
    monkeypatch.setattr(
        "ultrafast_memory.chat.service.create_llm_client", lambda config: FailingLLM()
    )

    response = handle_chat(ChatRequest(message="普通任务"))
    events = list(
        handle_chat_stream_ndjson(
            ChatRequest(message="普通流式任务", stream=True)
        )
    )

    assert response.workflow_state["agent_action"]["action"] == "final_answer"
    assert response.workflow_state["agent_action"]["error_details"][0]["type"] == "TimeoutError"
    assert "injected provider detail" not in response.assistant_message
    assert any(
        event.get("type") == "delta" and "现有状态未被修改" in event.get("content", "")
        for event in events
    )
    assert not any(event.get("type") == "error" for event in events)
