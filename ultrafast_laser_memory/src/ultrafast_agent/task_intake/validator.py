from __future__ import annotations

from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ALLOWED_TASK_FIELDS,
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)


class TaskFieldValidator:
    @classmethod
    def validate(
        cls,
        patch: TaskSpecPatch,
        current_spec: dict[str, Any],
        context: ClarificationContext,
    ) -> TaskSpecPatch:
        accepted: list[TaskFieldCandidate] = []
        rejected = list(patch.rejected_candidates)
        proposed_process = next(
            (
                item.normalized_value
                for item in patch.updates
                if item.field_name == "process_type" and item.normalized_value is not None
            ),
            current_spec.get("process_type"),
        )
        for candidate in patch.updates:
            reason = cls._rejection_reason(candidate, proposed_process)
            if reason:
                rejected.append(
                    {
                        "field_name": candidate.field_name,
                        "evidence": candidate.evidence,
                        "reason": reason,
                    }
                )
            else:
                accepted.append(candidate)
        covered = {item.field_name for item in accepted}
        unresolved = list(dict.fromkeys([
            *patch.unresolved_fields,
            *[field for field in context.pending_fields if field not in covered and current_spec.get(field) is None],
        ]))
        return patch.model_copy(
            update={"updates": accepted, "rejected_candidates": rejected, "unresolved_fields": unresolved}
        )

    @staticmethod
    def _rejection_reason(candidate: TaskFieldCandidate, process_type: Any) -> str | None:
        if candidate.field_name not in ALLOWED_TASK_FIELDS:
            return "field_not_allowed"
        value = candidate.normalized_value
        if candidate.operation != "clear" and value is None:
            return "normalized_value_missing"
        if candidate.field_name in {"thickness_mm", "cut_length_mm"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                return "length_must_be_positive"
        if candidate.field_name == "layer_cut_allowed" and not isinstance(value, bool):
            return "boolean_required"
        if candidate.field_name in {"cut_length_mm", "layer_cut_allowed", "contour_type"}:
            if process_type != "cutting":
                return "field_not_applicable_to_process"
        if not candidate.evidence.strip():
            return "evidence_required"
        return None

