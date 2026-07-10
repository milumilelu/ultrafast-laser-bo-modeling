from __future__ import annotations

import time

from ultrafast_agent.runtime import (
    RunContext,
    ToolContract,
    ToolRegistry,
    WorkflowDefinition,
    WorkflowRunner,
    WorkflowStep,
)


def test_runtime_emits_monotonic_redacted_real_tool_events():
    registry = ToolRegistry()
    registry.register(
        ToolContract(
            name="add",
            purpose="Add two values",
            handler=lambda payload, context: {
                "sum": payload["a"] + payload["b"],
                "api_key": "must-not-leak",
                "hidden_reasoning": "must-not-exist",
            },
        )
    )
    workflow = WorkflowDefinition(
        "math",
        (
            WorkflowStep(
                "add_values",
                "add",
                output_key="result",
                input_builder=lambda data: {"a": data["a"], "b": data["b"]},
                skill="calculation",
            ),
        ),
    )

    result = WorkflowRunner(registry).run(workflow, RunContext({"a": 2, "b": 3}))

    assert result.status == "completed"
    assert result.data["result"]["sum"] == 5
    assert [event["sequence"] for event in result.events] == list(range(1, len(result.events) + 1))
    rendered = str(result.events)
    assert "must-not-leak" not in rendered
    assert "must-not-exist" not in rendered
    assert any(event["event_type"] == "tool_started" and event["tool_name"] == "add" for event in result.events)
    assert any(event["event_type"] == "tool_completed" and event["duration_ms"] is not None for event in result.events)
    assert all(event["trace_id"] == result.run_id for event in result.events)
    assert all(event["visibility"] == "public" for event in result.events)


def test_runtime_retries_then_succeeds():
    attempts = {"count": 0}

    def flaky(payload, context):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(ToolContract("flaky", "Flaky test tool", flaky))
    workflow = WorkflowDefinition(
        "retry",
        (WorkflowStep("flaky_step", "flaky", output_key="value", retries=1),),
    )

    result = WorkflowRunner(registry).run(workflow, RunContext({}))

    assert result.status == "completed"
    assert attempts["count"] == 2
    assert any(event["status"] == "retrying" for event in result.events)


def test_runtime_timeout_fails_closed():
    def slow(payload, context):
        time.sleep(0.2)
        return {"late": True}

    registry = ToolRegistry()
    registry.register(ToolContract("slow", "Slow test tool", slow, timeout_ms=20))
    workflow = WorkflowDefinition("timeout", (WorkflowStep("slow_step", "slow"),))

    result = WorkflowRunner(registry).run(workflow, RunContext({}))

    assert result.status == "failed"
    assert "WorkflowTimeout" in (result.error or "")
    assert result.events[-1]["event_type"] == "workflow_failed"


def test_runtime_stream_can_be_cancelled():
    def slow(payload, context):
        time.sleep(0.3)
        return {"late": True}

    registry = ToolRegistry()
    registry.register(ToolContract("slow", "Slow test tool", slow, timeout_ms=1000))
    workflow = WorkflowDefinition("cancel", (WorkflowStep("slow_step", "slow"),))
    context = RunContext({})
    stream = WorkflowRunner(registry).stream(workflow, context)

    first = next(stream)
    context.cancellation.cancel()
    remaining = list(stream)

    assert first["event_type"] == "workflow_started"
    assert remaining[-1]["status"] == "cancelled"


def test_runtime_executes_declared_independent_steps_in_parallel():
    def delayed(payload, context):
        time.sleep(0.12)
        return {"value": payload["value"]}

    registry = ToolRegistry()
    registry.register(ToolContract("delayed", "Parallel timing probe", delayed))
    workflow = WorkflowDefinition(
        "parallel",
        (
            WorkflowStep(
                "left",
                "delayed",
                output_key="left_result",
                input_builder=lambda data: {"value": "left"},
                parallel_group="prefetch",
            ),
            WorkflowStep(
                "right",
                "delayed",
                output_key="right_result",
                input_builder=lambda data: {"value": "right"},
                parallel_group="prefetch",
            ),
        ),
    )

    started = time.perf_counter()
    result = WorkflowRunner(registry).run(workflow, RunContext({}))
    elapsed = time.perf_counter() - started

    assert result.status == "completed"
    assert result.data["left_result"]["value"] == "left"
    assert result.data["right_result"]["value"] == "right"
    assert elapsed < 0.21


def test_runtime_timeout_can_return_declared_bounded_fallback():
    def slow(payload, context):
        time.sleep(0.1)
        return {"late": True}

    registry = ToolRegistry()
    registry.register(ToolContract("bo", "BO timeout probe", slow, timeout_ms=10))
    workflow = WorkflowDefinition(
        "bo-fallback",
        (
            WorkflowStep(
                "bo_recommendation",
                "bo",
                output_key="bo_result",
                fallback_builder=lambda error, data: {
                    "model_status": "blocked",
                    "bo_invoked": False,
                    "search_space": data["machine_bounds"],
                    "reason": type(error).__name__,
                },
            ),
        ),
    )

    result = WorkflowRunner(registry).run(
        workflow, RunContext({"machine_bounds": {"laser_power_W": [1, 2]}})
    )

    assert result.status == "completed"
    assert result.data["bo_result"]["model_status"] == "blocked"
    assert result.data["bo_result"]["search_space"] == {"laser_power_W": [1, 2]}
    assert any(event["event_type"] == "fallback" for event in result.events)
