from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
import uuid


WORKFLOW_EVENT_TYPES = frozenset(
    {
        "workflow_started",
        "stage_changed",
        "slot_extracted",
        "clarification_required",
        "tool_started",
        "tool_succeeded",
        "tool_failed",
        "recommendation_created",
        "recommendation_blocked",
        "review_required",
        "job_created",
        "job_progressed",
        "workflow_completed",
        "workflow_blocked",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    event_id: str
    sequence: int
    session_id: str
    workflow_id: str
    event_type: str
    public_summary: str
    payload: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("workflow event sequence must be positive")
        if self.event_type not in WORKFLOW_EVENT_TYPES:
            raise ValueError(f"unsupported workflow event type: {self.event_type}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    session_id: str
    workflow_id: str
    workflow_type: str
    stage: str
    task_spec: dict[str, Any] = field(default_factory=dict)
    collected_slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: tuple[str, ...] = ()
    evidence_state: dict[str, Any] = field(default_factory=dict)
    recommendation_state: dict[str, Any] = field(default_factory=dict)
    trial_state: dict[str, Any] = field(default_factory=dict)
    production_state: dict[str, Any] = field(default_factory=dict)
    pending_actions: tuple[dict[str, Any], ...] = ()
    public_trace: tuple[dict[str, Any], ...] = ()
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    sequence: int = 0

    @classmethod
    def create(cls, session_id: str, workflow_type: str, stage: str = "created") -> "WorkflowContext":
        return cls(
            session_id=session_id,
            workflow_id=f"workflow_{uuid.uuid4().hex}",
            workflow_type=workflow_type,
            stage=stage,
        )

    def transition(
        self,
        event_type: str,
        public_summary: str,
        *,
        stage: str | None = None,
        payload: dict[str, Any] | None = None,
        updates: dict[str, Any] | None = None,
    ) -> tuple["WorkflowContext", WorkflowEvent]:
        next_sequence = self.sequence + 1
        event = WorkflowEvent(
            event_id=f"workflow_event_{uuid.uuid4().hex}",
            sequence=next_sequence,
            session_id=self.session_id,
            workflow_id=self.workflow_id,
            event_type=event_type,
            public_summary=public_summary,
            payload=dict(payload or {}),
            created_at=_now(),
        )
        allowed = {
            "task_spec",
            "collected_slots",
            "missing_slots",
            "evidence_state",
            "recommendation_state",
            "trial_state",
            "production_state",
            "pending_actions",
        }
        changes = dict(updates or {})
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported workflow context updates: {sorted(unknown)}")
        if "missing_slots" in changes:
            changes["missing_slots"] = tuple(changes["missing_slots"])
        if "pending_actions" in changes:
            changes["pending_actions"] = tuple(changes["pending_actions"])
        trace = (*self.public_trace, event.to_dict())
        return (
            replace(
                self,
                stage=stage or self.stage,
                public_trace=trace,
                sequence=next_sequence,
                updated_at=event.created_at,
                **changes,
            ),
            event,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["missing_slots"] = list(self.missing_slots)
        value["pending_actions"] = list(self.pending_actions)
        value["public_trace"] = list(self.public_trace)
        return value

