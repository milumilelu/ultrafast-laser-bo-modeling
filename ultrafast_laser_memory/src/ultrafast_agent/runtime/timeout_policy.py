from __future__ import annotations


class WorkflowTimeout(TimeoutError):
    """Raised when a real tool call exceeds its public timeout contract."""


def resolve_timeout_ms(step_timeout_ms: int | None, tool_timeout_ms: int) -> int:
    value = step_timeout_ms if step_timeout_ms is not None else tool_timeout_ms
    if value <= 0:
        raise ValueError("timeout_ms must be positive")
    return value
