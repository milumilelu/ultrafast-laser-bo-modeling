from __future__ import annotations

import unicodedata
from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ALLOWED_TASK_FIELDS,
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)


_PROCESS_TYPES = {
    "cutting", "drilling", "hole_drilling", "engraving", "ablation",
    "femtosecond_laser_micromachining",
}
_CONTOUR_TYPES = {"straight", "curve", "arc", "circle"}
_AUXILIARY_TYPES = {"compressed_air", "nitrogen", "oxygen", "argon", "none"}
_CORRECTION_MARKERS = ("改为", "改成", "更正", "说错了", "不是", "应为")


class TaskSpecPatchValidator:
    @classmethod
    def validate(
        cls,
        patch: TaskSpecPatch,
        current_spec: dict[str, Any],
        context: ClarificationContext,
        user_message: str | None = None,
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
            reason = cls._rejection_reason(candidate, proposed_process, user_message)
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
        degraded = patch.degraded or bool(patch.llm_attempted and rejected and not accepted)
        return patch.model_copy(update={
            "updates": accepted,
            "rejected_candidates": rejected,
            "unresolved_fields": unresolved,
            "degraded": degraded,
        })

    @staticmethod
    def _rejection_reason(
        candidate: TaskFieldCandidate,
        process_type: Any,
        user_message: str | None,
    ) -> str | None:
        if candidate.field_name not in ALLOWED_TASK_FIELDS:
            return "field_not_allowed"
        value = candidate.normalized_value
        if value is None:
            return "normalized_value_missing"
        if candidate.field_name in {
            "thickness_mm", "cut_length_mm", "hole_diameter_mm", "hole_depth_mm"
        }:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                return "length_must_be_positive"
        if candidate.field_name in {"layer_cut_allowed", "through_hole"} and not isinstance(value, bool):
            return "boolean_required"
        if candidate.field_name == "process_type" and value not in _PROCESS_TYPES:
            return "process_type_not_allowed"
        if candidate.field_name == "contour_type" and value not in _CONTOUR_TYPES:
            return "contour_type_not_allowed"
        if candidate.field_name == "auxiliary" and value not in _AUXILIARY_TYPES:
            return "auxiliary_not_allowed"
        if candidate.field_name in {
            "material", "quality_requirement", "efficiency_requirement", "objective",
            "taper_requirement", "entrance_quality", "exit_quality",
        }:
            if not isinstance(value, str) or not value.strip():
                return "non_empty_string_required"
        if candidate.field_name in {"cut_length_mm", "layer_cut_allowed", "contour_type"}:
            if process_type != "cutting":
                return "field_not_applicable_to_process"
        if candidate.field_name in {
            "hole_diameter_mm", "hole_depth_mm", "through_hole", "taper_requirement",
            "entrance_quality", "exit_quality",
        } and process_type not in {"drilling", "hole_drilling"}:
            return "field_not_applicable_to_process"
        if not candidate.evidence.strip():
            return "evidence_required"
        if user_message is not None and not TaskSpecPatchValidator._evidence_present(
            candidate.evidence, user_message
        ):
            return "evidence_not_in_user_message"
        if candidate.operation == "correct" and not any(
            marker in candidate.evidence for marker in _CORRECTION_MARKERS
        ):
            return "correction_evidence_required"
        return None

    @staticmethod
    def _evidence_present(evidence: str, message: str) -> bool:
        normalized_evidence = "".join(unicodedata.normalize("NFKC", evidence).split())
        normalized_message = "".join(unicodedata.normalize("NFKC", message).split())
        return bool(normalized_evidence and normalized_evidence in normalized_message)


# Import compatibility for callers created before the validator rename.
TaskFieldValidator = TaskSpecPatchValidator
