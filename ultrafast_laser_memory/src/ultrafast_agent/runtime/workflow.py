from __future__ import annotations

import queue
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable, Iterator

from ultrafast_agent.runtime.event_bus import EventBus
from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_agent.runtime.cancellation import WorkflowCancelled
from ultrafast_agent.runtime.execution_context import RunContext
from ultrafast_agent.runtime.retry_policy import attempt_count
from ultrafast_agent.runtime.timeout_policy import WorkflowTimeout, resolve_timeout_ms
from ultrafast_agent.runtime.tools import ToolContract, ToolRegistry


InputBuilder = Callable[[dict[str, Any]], dict[str, Any]]
Condition = Callable[[dict[str, Any]], bool]
FallbackBuilder = Callable[[Exception, dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    name: str
    tool: str
    output_key: str | None = None
    input_builder: InputBuilder = lambda data: data
    condition: Condition = lambda data: True
    timeout_ms: int | None = None
    retries: int = 0
    continue_on_error: bool = False
    skill: str | None = None
    parallel_group: str | None = None
    fallback_builder: FallbackBuilder | None = None


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    name: str
    steps: tuple[WorkflowStep, ...]


@dataclass(slots=True)
class WorkflowResult:
    run_id: str
    workflow: str
    status: str
    data: dict[str, Any]
    events: list[dict[str, Any]]
    error: str | None = None


class WorkflowRunner:
    def __init__(self, registry: ToolRegistry, event_bus_factory: Callable[[str], EventBus] = EventBus):
        self.registry = registry
        self.event_bus_factory = event_bus_factory

    def run(
        self,
        workflow: WorkflowDefinition,
        context: RunContext,
        *,
        event_bus: EventBus | None = None,
    ) -> WorkflowResult:
        bus = event_bus or self.event_bus_factory(context.run_id)
        started = time.perf_counter()
        bus.emit(
            "workflow_started",
            stage="workflow",
            title="工作流开始",
            summary=workflow.name,
            status="running",
            progress=0,
            data={"workflow": workflow.name},
        )
        error: str | None = None
        status = "completed"
        total = max(1, len(workflow.steps))
        index = 0
        while index < len(workflow.steps):
            step = workflow.steps[index]
            if context.cancellation.cancelled:
                status = "cancelled"
                error = "workflow cancelled"
                bus.emit(
                    "warning",
                    stage=step.name,
                    title="工作流已取消",
                    summary=error,
                    status=status,
                    progress=int(index / total * 100),
                )
                break
            if step.parallel_group:
                group_end = index + 1
                while (
                    group_end < len(workflow.steps)
                    and workflow.steps[group_end].parallel_group == step.parallel_group
                ):
                    group_end += 1
                group = list(enumerate(workflow.steps[index:group_end], start=index))
                runnable = []
                for group_index, group_step in group:
                    if group_step.condition(context.data):
                        runnable.append((group_index, group_step))
                    else:
                        self._emit_skipped(group_step, bus, group_index, total)
                failure: tuple[WorkflowStep, Exception] | None = None
                with ThreadPoolExecutor(
                    max_workers=max(1, len(runnable)),
                    thread_name_prefix=f"parallel-{step.parallel_group}",
                ) as executor:
                    futures = [
                        (
                            group_step,
                            executor.submit(
                                self._run_step,
                                group_step,
                                context,
                                bus,
                                group_index,
                                total,
                            ),
                        )
                        for group_index, group_step in runnable
                    ]
                    for group_step, future in futures:
                        try:
                            self._store_output(context, group_step, future.result())
                        except Exception as exc:
                            if group_step.fallback_builder is not None:
                                self._apply_fallback(group_step, exc, context, bus)
                            elif group_step.continue_on_error:
                                context.data.setdefault("workflow_errors", []).append(
                                    {
                                        "step": group_step.name,
                                        "error": f"{type(exc).__name__}: {exc}",
                                    }
                                )
                            elif failure is None:
                                failure = (group_step, exc)
                index = group_end
                if failure is not None:
                    failed_step, exc = failure
                    error = f"{type(exc).__name__}: {exc}"
                    status = "cancelled" if isinstance(exc, WorkflowCancelled) else "failed"
                    break
                continue
            if not step.condition(context.data):
                self._emit_skipped(step, bus, index, total)
                index += 1
                continue
            try:
                output = self._run_step(step, context, bus, index, total)
                self._store_output(context, step, output)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if step.fallback_builder is not None:
                    self._apply_fallback(step, exc, context, bus)
                    error = None
                    index += 1
                    continue
                if step.continue_on_error:
                    context.data.setdefault("workflow_errors", []).append(
                        {"step": step.name, "error": error}
                    )
                    index += 1
                    continue
                status = "cancelled" if isinstance(exc, WorkflowCancelled) else "failed"
                break
            index += 1
        duration_ms = (time.perf_counter() - started) * 1000
        bus.emit(
            "workflow_completed" if status == "completed" else "workflow_failed",
            stage="workflow",
            title="工作流完成" if status == "completed" else "工作流失败",
            summary=workflow.name if error is None else error,
            status=status,
            progress=100 if status == "completed" else None,
            duration_ms=duration_ms,
            data={"workflow": workflow.name},
        )
        return WorkflowResult(
            run_id=context.run_id,
            workflow=workflow.name,
            status=status,
            data=context.data,
            events=[event.to_dict() for event in bus.events],
            error=error,
        )

    @staticmethod
    def _store_output(context: RunContext, step: WorkflowStep, output: Any) -> None:
        if step.output_key:
            context.data[step.output_key] = output
        elif isinstance(output, dict):
            context.data.update(output)

    def _apply_fallback(
        self,
        step: WorkflowStep,
        error: Exception,
        context: RunContext,
        bus: EventBus,
    ) -> None:
        assert step.fallback_builder is not None
        output = step.fallback_builder(error, context.data)
        self._store_output(context, step, output)
        bus.emit(
            "fallback",
            stage=step.name,
            title="工具降级",
            summary=f"{type(error).__name__}; deterministic fallback applied",
            status="completed",
            skill=step.skill,
            tool=step.tool,
            data={"output_summary": _summary(output)},
        )

    @staticmethod
    def _emit_skipped(
        step: WorkflowStep, bus: EventBus, index: int, total: int
    ) -> None:
        bus.emit(
            "state_updated",
            stage=step.name,
            title="跳过步骤",
            summary=step.name,
            status="skipped",
            progress=int(index / total * 100),
            skill=step.skill,
            tool=step.tool,
        )

    def stream(self, workflow: WorkflowDefinition, context: RunContext) -> Iterator[dict[str, Any]]:
        bus = self.event_bus_factory(context.run_id)
        channel: queue.Queue[AgentEvent | object] = queue.Queue()
        sentinel = object()
        unsubscribe = bus.subscribe(channel.put)

        def execute() -> None:
            try:
                self.run(workflow, context, event_bus=bus)
            finally:
                channel.put(sentinel)

        thread = Thread(target=execute, name=f"workflow-{context.run_id}", daemon=True)
        thread.start()
        try:
            while True:
                item = channel.get()
                if item is sentinel:
                    break
                assert isinstance(item, AgentEvent)
                yield item.to_dict()
        finally:
            unsubscribe()

    def _run_step(
        self,
        step: WorkflowStep,
        context: RunContext,
        bus: EventBus,
        index: int,
        total: int,
    ) -> Any:
        contract = self.registry.get(step.tool)
        payload = step.input_builder(context.data)
        timeout_ms = resolve_timeout_ms(step.timeout_ms, contract.timeout_ms)
        attempts = attempt_count(step.retries)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            bus.emit(
                "tool_started",
                stage=step.name,
                title="调用工具",
                summary=contract.purpose,
                status="running",
                progress=int(index / total * 100),
                skill=step.skill,
                tool=contract.name,
                attempt=attempt,
                data={"input_summary": _summary(payload)},
            )
            try:
                output = self._invoke(contract, payload, context, timeout_ms)
            except Exception as exc:
                last_error = exc
                bus.emit(
                    "tool_failed",
                    stage=step.name,
                    title="工具调用失败",
                    summary=f"{type(exc).__name__}: {exc}",
                    status="failed" if attempt == attempts else "retrying",
                    progress=int(index / total * 100),
                    skill=step.skill,
                    tool=contract.name,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    attempt=attempt,
                )
                if attempt < attempts:
                    continue
                raise
            bus.emit(
                "tool_completed",
                stage=step.name,
                title="工具调用完成",
                summary=contract.purpose,
                status="completed",
                progress=int((index + 1) / total * 100),
                skill=step.skill,
                tool=contract.name,
                duration_ms=(time.perf_counter() - started) * 1000,
                attempt=attempt,
                data={"output_summary": _summary(output)},
            )
            return output
        raise last_error or RuntimeError("tool call failed")

    def _invoke(
        self,
        contract: ToolContract,
        payload: dict[str, Any],
        context: RunContext,
        timeout_ms: int,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{contract.name}")
        future: Future[Any] = executor.submit(contract.handler, payload, context.data)
        deadline = time.perf_counter() + timeout_ms / 1000
        try:
            while True:
                if context.cancellation.cancelled:
                    future.cancel()
                    raise WorkflowCancelled("workflow cancelled")
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    future.cancel()
                    raise WorkflowTimeout(f"tool timed out after {timeout_ms} ms: {contract.name}")
                try:
                    return future.result(timeout=min(0.05, remaining))
                except FutureTimeoutError:
                    continue
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def _summary(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, dict):
        return f"mapping(keys={','.join(sorted(map(str, value.keys()))[:12])})"
    if isinstance(value, (list, tuple, set)):
        return f"{type(value).__name__}(count={len(value)})"
    text = str(value)
    return text if len(text) <= 160 else text[:157] + "..."
