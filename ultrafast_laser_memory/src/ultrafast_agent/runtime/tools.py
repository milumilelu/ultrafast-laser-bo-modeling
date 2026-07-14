from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
import time
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ToolContract:
    name: str
    purpose: str
    handler: ToolHandler
    version: str = "1.0"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effect_level: str = "none"
    timeout_ms: int = 30_000
    side_effects: tuple[str, ...] = ()
    retry_policy: dict[str, Any] = field(default_factory=lambda: {"max_attempts": 1})
    async_capable: bool = False
    enabled: bool = True
    cache_policy: str = "none"
    sensitive_input_fields: tuple[str, ...] = field(default_factory=tuple)
    permission_level: int = 1
    requires_human_approval: bool = False
    prohibited: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolContract] = {}

    def register(self, contract: ToolContract, *, replace: bool = False) -> None:
        if contract.name in self._tools and not replace:
            raise ValueError(f"tool already registered: {contract.name}")
        self._tools[contract.name] = contract

    def get(self, name: str) -> ToolContract:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc

    def list_contracts(self) -> list[ToolContract]:
        return [self._tools[name] for name in sorted(self._tools)]

    def call(self, name: str, payload: dict[str, Any], context: dict[str, Any]) -> Any:
        return self.get(name).handler(payload, context)


@dataclass(slots=True)
class ToolExecutionResult:
    status: str
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    attempt: int = 1
    duration_ms: float = 0.0


class ToolExecutor:
    """Single validation/timeout/retry boundary for synchronous application tools."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute(
        self,
        name: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> ToolExecutionResult:
        contract = self.registry.get(name)
        if contract.prohibited or contract.permission_level >= 4:
            return ToolExecutionResult(
                "failed",
                error_code="tool_prohibited",
                error_message=f"tool is prohibited: {name}",
            )
        if contract.requires_human_approval and not bool((context or {}).get("human_approved")):
            return ToolExecutionResult(
                "failed",
                error_code="human_approval_required",
                error_message=f"human approval required: {name}",
            )
        if not contract.enabled:
            return ToolExecutionResult("failed", error_code="tool_disabled", error_message=f"tool disabled: {name}")
        validation_error = _validate_required(payload, contract.input_schema)
        if validation_error:
            return ToolExecutionResult("failed", error_code="validation_failed", error_message=validation_error)
        attempts = max(1, int(contract.retry_policy.get("max_attempts", 1)))
        retryable = set(contract.retry_policy.get("retryable_errors", ("timeout", "provider_unavailable")))
        started = time.perf_counter()
        last: ToolExecutionResult | None = None
        for attempt in range(1, attempts + 1):
            if cancellation_requested and cancellation_requested():
                return ToolExecutionResult("cancelled", error_code="cancelled", error_message="tool execution cancelled", attempt=attempt)
            try:
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(contract.handler, dict(payload), dict(context or {}))
                try:
                    output = future.result(timeout=max(contract.timeout_ms, 1) / 1000)
                except FutureTimeout:
                    future.cancel()
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool = None
                    raise
                finally:
                    if pool is not None:
                        pool.shutdown(wait=True)
                output_error = _validate_required(output, contract.output_schema) if isinstance(output, dict) else None
                if output_error:
                    return ToolExecutionResult("failed", error_code="validation_failed", error_message=output_error, attempt=attempt)
                return ToolExecutionResult(
                    "succeeded",
                    output=output,
                    attempt=attempt,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            except FutureTimeout:
                last = ToolExecutionResult("failed", error_code="timeout", error_message=f"tool timed out: {name}", attempt=attempt)
            except Exception as exc:  # noqa: BLE001 - mapped at the execution boundary
                code = getattr(exc, "code", "tool_failed")
                last = ToolExecutionResult("failed", error_code=str(code), error_message=str(exc), attempt=attempt)
            if last.error_code not in retryable:
                break
        assert last is not None
        last.duration_ms = (time.perf_counter() - started) * 1000
        return last


def _validate_required(value: dict[str, Any], schema: dict[str, Any]) -> str | None:
    required = schema.get("required", []) if schema else []
    missing = [name for name in required if name not in value or value[name] is None]
    return f"missing required fields: {', '.join(missing)}" if missing else None
