from __future__ import annotations

from typing import Any

from ultrafast_agent.runtime import ToolContract
from ultrafast_agent.task_intake.missing_field_service import MissingFieldEvaluator
from ultrafast_agent.task_intake.normalizer import TaskFieldNormalizer
from ultrafast_agent.task_intake.schemas import (
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)
from ultrafast_agent.task_intake.validator import TaskSpecPatchValidator
from ultrafast_agent.task_intake.merge_service import TaskSpecMergeService
from ultrafast_memory.chat.session_state import get_session_state, update_session_state


TOOL_VERSION = "agent-update-task-context-v2"


def update_task_context(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Validate and commit already-structured Agent interpretations to canonical TaskSpec."""
    session_id = str(context["session_id"])
    user_message = str(context["user_message"])
    clarification = ClarificationContext.model_validate(context["clarification_context"])
    state = get_session_state(session_id)
    collected = dict(state.get("collected_slots") or {})
    current_spec = dict(collected.get("process_task_spec") or {})

    candidates: list[TaskFieldCandidate] = []
    rejected: list[dict[str, Any]] = []
    for raw in payload.get("updates") or []:
        if not isinstance(raw, dict):
            rejected.append({"field_name": "unknown", "reason": "update_not_object"})
            continue
        try:
            candidates.append(TaskFieldCandidate(
                field_name=str(raw.get("field_name") or ""),
                raw_value=raw.get("value", raw.get("raw_value")),
                unit=raw.get("unit"),
                evidence=str(raw.get("evidence") or ""),
                extraction_source="main_agent_tool_call",
                confidence=float(raw.get("confidence", 1.0)),
                operation=str(raw.get("operation") or "fill"),
            ))
        except (TypeError, ValueError) as exc:
            rejected.append({
                "field_name": str(raw.get("field_name") or "unknown"),
                "reason": f"invalid_update:{type(exc).__name__}",
            })

    patch = TaskSpecPatch(
        updates=candidates,
        rejected_candidates=rejected,
        extraction_version=TOOL_VERSION,
        extraction_mode="llm_structured",
        llm_attempted=True,
        schema_valid=True,
    )
    normalized = TaskFieldNormalizer.normalize(patch)
    validated = TaskSpecPatchValidator.validate(
        normalized,
        current_spec,
        clarification,
        user_message=user_message,
    )
    merged = TaskSpecMergeService.merge(
        current_spec,
        validated,
        current_provenance=collected.get("process_task_field_provenance") or {},
        revision_history=collected.get("process_task_revision_history") or [],
        message_id=context.get("message_id"),
        context=clarification,
    )
    projected_spec = _with_geometry_projection(merged.task_spec)
    remaining = MissingFieldEvaluator.evaluate(projected_spec, clarification)
    collected.update({
        "process_task_spec": projected_spec,
        "task_spec": projected_spec,
        "process_task_field_provenance": merged.field_provenance,
        "process_task_revision_history": merged.revision_history,
    })
    update_session_state(session_id, {"collected_slots": collected})

    rejected_items = list(validated.rejected_candidates)
    status = "success" if not rejected_items and not merged.conflicts else "partial"
    return {
        "status": status,
        "applied": [item.field_name for item in merged.applied],
        "unchanged": [item.field_name for item in merged.unchanged],
        "rejected": rejected_items,
        "conflicts": merged.conflicts,
        "remaining_missing": remaining,
        "task_spec": projected_spec,
        "field_provenance": merged.field_provenance,
        "revision_history": merged.revision_history,
    }


def update_task_context_contract() -> ToolContract:
    return ToolContract(
        name="update_task_context",
        purpose="Validate and commit progressive structured task facts with provenance.",
        handler=update_task_context,
        version=TOOL_VERSION,
        input_schema={
            "type": "object",
            "required": ["updates"],
            "properties": {
                "updates": {
                    "type": "array",
                    "description": "All explicit facts from the current user message in one call.",
                    "items": {
                        "type": "object",
                        "required": ["field_name", "value", "evidence"],
                        "properties": {
                            "field_name": {"type": "string"},
                            "value": {
                                "description": "For geometry use {feature_type, dimensions: {*_mm}, depth_mm, description}."
                            },
                            "unit": {"type": ["string", "null"]},
                            "evidence": {"type": "string"},
                            "operation": {"type": "string", "enum": ["fill", "correct"]},
                        },
                    },
                }
            },
        },
        output_schema={
            "type": "object",
            "required": ["status", "applied", "rejected", "conflicts", "remaining_missing"],
        },
        side_effect_level="session_state_write",
        side_effects=("canonical_task_spec", "field_provenance", "revision_history"),
        timeout_ms=5_000,
        permission_level=2,
        exposed_by_default=True,
    )


def _with_geometry_projection(task_spec: dict[str, Any]) -> dict[str, Any]:
    """Project older hole fields into the generic geometry object at the boundary."""
    result = dict(task_spec)
    geometry = dict(result.get("geometry") or {})
    if any(name in result for name in ("hole_diameter_mm", "hole_depth_mm", "through_hole")):
        geometry.setdefault("feature_type", "hole")
        dimensions = dict(geometry.get("dimensions") or {})
        if "hole_diameter_mm" in result:
            dimensions.setdefault("diameter_mm", result["hole_diameter_mm"])
        if dimensions:
            geometry["dimensions"] = dimensions
        if "hole_depth_mm" in result:
            geometry.setdefault("depth_mm", result["hole_depth_mm"])
        if "through_hole" in result:
            geometry.setdefault("through", result["through_hole"])
    if geometry:
        result["geometry"] = geometry
    return result
