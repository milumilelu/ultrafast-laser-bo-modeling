from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.core.time_utils import utc_now_iso


class WorkingContext(BaseModel):
    """Open-world, partial task state owned by the main Agent loop."""

    model_config = ConfigDict(extra="allow")

    task: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    active_skills: list[str] = Field(default_factory=list)
    equipment_context: dict[str, Any] | None = None
    pending_user_action: dict[str, Any] | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)

    def apply(self, updates: dict[str, Any]) -> list[str]:
        changed: list[str] = []
        for key, value in deepcopy(updates).items():
            current = getattr(self, key, None)
            if isinstance(current, dict) and isinstance(value, dict):
                merged = deepcopy(current)
                _deep_merge(merged, value, changed, key)
                setattr(self, key, merged)
            elif current != value:
                setattr(self, key, value)
                changed.append(key)
        return changed


class ContextPersistenceService:
    """Persist projections and provenance; callers deliberately treat failures as warnings."""

    def persist(
        self,
        session_id: str,
        context: WorkingContext,
        *,
        changed_paths: list[str],
        message_id: str | None,
        final_action: dict[str, Any] | None = None,
        decision_count: int | None = None,
    ) -> None:
        snapshot = context.model_dump(mode="json")
        provenance = {
            "message_id": message_id,
            "changed_paths": changed_paths,
            "recorded_at": utc_now_iso(),
        }
        state = get_session_state(session_id)
        revisions = list(state.get("working_context_revisions_json") or [])
        revisions.append(provenance)
        state_update = {
            "working_context_json": snapshot,
            "active_skills_json": context.active_skills,
            "agent_observations_json": context.observations[-100:],
            "working_context_revisions_json": revisions[-100:],
            "collected_slots": {
                "working_context": snapshot,
                # Read-only UI/report projection; it is not a validation gate.
                "task_spec": snapshot["task"],
                "process_task_spec": snapshot["task"],
            },
        }
        if final_action is not None:
            state_update["last_agent_action_json"] = final_action
            state_update["collected_slots"]["process_workflow"] = {
                "last_agent_action": final_action,
                "missing_slots": [],
            }
        if decision_count is not None:
            state_update["agent_decision_count"] = decision_count
        update_session_state(session_id, state_update)


def load_working_context(state: dict[str, Any]) -> WorkingContext:
    stored = state.get("working_context_json")
    if isinstance(stored, dict) and stored:
        return WorkingContext.model_validate(stored)
    collected = dict(state.get("collected_slots") or {})
    task = dict(collected.get("task_spec") or collected.get("process_task_spec") or {})
    return WorkingContext(
        task=task,
        observations=list(state.get("agent_observations_json") or [])[-100:],
        active_skills=list(state.get("active_skills_json") or []),
    )


def _deep_merge(target: dict[str, Any], updates: dict[str, Any], changed: list[str], prefix: str = "") -> None:
    for key, value in updates.items():
        path = f"{prefix}.{key}" if prefix else key
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _deep_merge(current, value, changed, path)
        elif current != value:
            target[key] = value
            changed.append(path)
