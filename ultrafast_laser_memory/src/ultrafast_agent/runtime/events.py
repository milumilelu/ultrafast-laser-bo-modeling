from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


FORBIDDEN_KEYS = {
    "chain_of_thought",
    "raw_thoughts",
    "hidden_reasoning",
    "model_reasoning_tokens",
    "system_prompt",
    "api_key",
    "authorization",
    "password",
    "secret",
    "dpapi",
}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in FORBIDDEN_KEYS or any(
        token in lowered for token in ("api_key", "password", "authorization", "secret", "dpapi")
    )


def redact_public_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if _is_sensitive_key(str(key)) else redact_public_data(item)
            for key, item in value.items()
            if str(key).lower() not in {"chain_of_thought", "raw_thoughts", "hidden_reasoning", "system_prompt"}
        }
    if isinstance(value, (list, tuple)):
        return [redact_public_data(item) for item in value]
    return value


@dataclass(slots=True)
class AgentEvent:
    run_id: str
    sequence: int
    event_type: str
    stage: str
    title: str
    summary: str
    status: str
    event_id: str = field(default_factory=lambda: f"agent-event-{uuid.uuid4().hex}")
    trace_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    message_id: str | None = None
    task_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    progress: int | None = None
    skill: str | None = None
    step: str | None = None
    tool: str | None = None
    tool_name: str | None = None
    duration_ms: float | None = None
    cache_hit: bool | None = None
    attempt: int | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    parent_event_id: str | None = None
    visibility: str = "public"
    data: dict[str, Any] = field(default_factory=dict)
    public_summary: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trace_id = self.trace_id or self.run_id
        self.tool_name = self.tool_name or self.tool
        self.public_summary = self.public_summary or self.summary
        self.payload = self.payload or self.data

    def to_dict(self) -> dict[str, Any]:
        value = redact_public_data(asdict(self))
        value["created_at"] = value["timestamp"]
        return value
