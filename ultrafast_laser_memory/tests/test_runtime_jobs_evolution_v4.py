from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import time

import pytest

from ultrafast_agent.evolution import EvolutionService
from ultrafast_agent.jobs import BackgroundJobService, JobWorker
from ultrafast_agent.runtime import ToolExecutor, WorkflowContext
from ultrafast_agent.runtime.tools import ToolContract, ToolRegistry
from ultrafast_integrations.storage.job_repository import SQLiteJobRepository
from ultrafast_integrations.storage.evolution_repository import SQLiteEvolutionRepository
from ultrafast_memory.db.init_db import init_database


def test_workflow_context_transition_is_immutable_and_monotonic():
    original = WorkflowContext.create("session-1", "task_intake")
    updated, event = original.transition("workflow_started", "started", stage="intake")
    assert original.stage == "created"
    assert updated.stage == "intake"
    assert event.sequence == 1 == updated.sequence
    with pytest.raises(FrozenInstanceError):
        updated.stage = "invalid"  # type: ignore[misc]


def test_tool_executor_validates_input_and_maps_timeout():
    registry = ToolRegistry()
    registry.register(ToolContract("echo", "test", lambda payload, _: payload, input_schema={"required": ["value"]}))
    executor = ToolExecutor(registry)
    assert executor.execute("echo", {}).error_code == "validation_failed"
    assert executor.execute("echo", {"value": 1}).output == {"value": 1}
    registry.register(ToolContract("slow", "test", lambda *_: time.sleep(0.2), timeout_ms=10))
    started = time.perf_counter()
    assert executor.execute("slow", {}).error_code == "timeout"
    assert time.perf_counter() - started < 0.15


def test_job_idempotency_worker_events_and_recovery(isolated_root):
    init_database()
    repository = SQLiteJobRepository()
    service = BackgroundJobService(repository)
    first, created = service.create("report", {"x": 1}, idempotency_key="same")
    second, created_again = service.create("report", {"x": 2}, idempotency_key="same")
    assert created is True and created_again is False and first.job_id == second.job_id
    worker = JobWorker(repository, {"report": lambda payload, context: {"x": payload["x"]}})
    assert worker.run_once().status == "succeeded"
    assert [event["sequence"] for event in repository.list_events(first.job_id)] == [1, 2, 3]

    stale, _ = service.create("report", {}, idempotency_key="stale")
    claimed = repository.claim_next()
    assert claimed and claimed.job_id == stale.job_id
    before = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    assert repository.recover_stale(before) == 1
    assert service.get(stale.job_id).status == "retrying"


def test_job_timeout_retry_and_cancellation_states(isolated_root):
    init_database()
    repository = SQLiteJobRepository()
    service = BackgroundJobService(repository)
    timed, _ = service.create("slow", {}, timeout_seconds=0.001)
    result = JobWorker(repository, {"slow": lambda *_: (time.sleep(0.01) or {})}).run_once()
    assert result.job_id == timed.job_id and result.status == "timed_out"
    assert service.retry(timed.job_id).status == "retrying"
    queued, _ = service.create("cancel", {})
    assert service.cancel(queued.job_id).status == "cancelled"


def test_evolution_requires_evaluation_and_approval_and_rolls_back():
    service = EvolutionService()
    base = service.register_artifact_version("router", "router_policy", {"threshold": 0.7}, status="active")
    candidate = service.create_evolution_candidate(
        "router_policy", "router", {"threshold": 0.8}, "improve routing", "manual_proposal",
        target_version_id=base.artifact_version_id,
    )
    with pytest.raises(ValueError):
        service.activate_version(candidate.candidate_id, activation_reason="bad", rollback_condition="regression")
    service.prepare_candidate(candidate.candidate_id)
    evaluation = service.run_evaluation(
        candidate.candidate_id, lambda *_: ({"accuracy": 1.0}, [], True),
        dataset_version="replay-v1", evaluator_version="router-eval-v1",
        reproducibility={"random_seed": 42, "code_version": "abc"},
    )
    assert evaluation.passed
    service.request_promotion(candidate.candidate_id)
    service.approve_promotion(candidate.candidate_id, "expert")
    active = service.activate_version(candidate.candidate_id, activation_reason="passed", rollback_condition="accuracy drop")
    assert active.status == "active" and active.parent_version_id == base.artifact_version_id
    restored = service.rollback_version("router", "regression")
    assert restored.artifact_version_id == base.artifact_version_id and restored.status == "active"


def test_evolution_state_survives_service_restart(isolated_root):
    init_database()
    first = EvolutionService(SQLiteEvolutionRepository())
    version = first.register_artifact_version("workflow", "workflow_policy", {"mode": "safe"}, status="active")
    second = EvolutionService(SQLiteEvolutionRepository())
    restored = second.get_active_version("workflow")
    assert restored is not None
    assert restored.artifact_version_id == version.artifact_version_id
    assert restored.content == {"mode": "safe"}
