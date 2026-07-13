from __future__ import annotations

from copy import deepcopy
from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ClarificationContext,
    MergeResult,
    TaskFieldCandidate,
    TaskSpecPatch,
)


class TaskSpecMergeService:
    @classmethod
    def merge(
        cls,
        current_spec: dict[str, Any],
        patch: TaskSpecPatch,
        *,
        current_provenance: dict[str, dict[str, Any]] | None = None,
        revision_history: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
        context: ClarificationContext | None = None,
    ) -> MergeResult:
        task = deepcopy(current_spec)
        provenance = deepcopy(current_provenance or {})
        revisions = deepcopy(revision_history or [])
        applied: list[TaskFieldCandidate] = []
        unchanged: list[TaskFieldCandidate] = []
        conflicts: list[dict[str, Any]] = []

        for candidate in patch.updates:
            field = candidate.field_name
            old = task.get(field)
            new = candidate.normalized_value
            if candidate.operation == "clear":
                if old is not None:
                    task.pop(field, None)
                    revisions.append(cls._revision(field, old, None, candidate, message_id))
                    applied.append(candidate)
                    provenance[field] = cls._metadata(candidate, message_id, context, patch.extraction_version)
                continue
            if old is None:
                task[field] = new
                applied.append(candidate)
                provenance[field] = cls._metadata(candidate, message_id, context, patch.extraction_version)
                continue
            if cls._same(old, new):
                unchanged.append(candidate)
                cls._append_evidence(provenance, field, candidate, message_id)
                continue
            if candidate.operation != "correct":
                conflicts.append(
                    {
                        "field_name": field,
                        "existing_value": old,
                        "candidate_value": new,
                        "evidence": candidate.evidence,
                        "operation": candidate.operation,
                        "reason": "confirmed_value_requires_explicit_correction",
                    }
                )
                continue
            task[field] = new
            applied.append(candidate)
            revisions.append(cls._revision(field, old, new, candidate, message_id))
            provenance[field] = cls._metadata(candidate, message_id, context, patch.extraction_version)

        return MergeResult(
            task_spec=task,
            field_provenance=provenance,
            revision_history=revisions,
            applied=applied,
            unchanged=unchanged,
            conflicts=conflicts,
        )

    @staticmethod
    def _same(old: Any, new: Any) -> bool:
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            return abs(float(old) - float(new)) < 1e-9
        return old == new

    @staticmethod
    def _metadata(
        candidate: TaskFieldCandidate,
        message_id: str | None,
        context: ClarificationContext | None,
        version: str,
    ) -> dict[str, Any]:
        return {
            "value": candidate.normalized_value,
            "unit": candidate.unit,
            "status": "confirmed",
            "source": candidate.extraction_source,
            "evidence": candidate.evidence,
            "evidence_history": [candidate.evidence],
            "confidence": candidate.confidence,
            "message_id": message_id,
            "clarification_round": context.clarification_round if context else 0,
            "extractor_version": version,
        }

    @staticmethod
    def _append_evidence(
        provenance: dict[str, dict[str, Any]],
        field: str,
        candidate: TaskFieldCandidate,
        message_id: str | None,
    ) -> None:
        meta = provenance.setdefault(field, {})
        evidence = meta.setdefault("evidence_history", [])
        if candidate.evidence not in evidence:
            evidence.append(candidate.evidence)
        meta["last_message_id"] = message_id

    @staticmethod
    def _revision(
        field: str,
        old: Any,
        new: Any,
        candidate: TaskFieldCandidate,
        message_id: str | None,
    ) -> dict[str, Any]:
        return {
            "field_name": field,
            "old_value": old,
            "new_value": new,
            "evidence": candidate.evidence,
            "source": candidate.extraction_source,
            "operation": candidate.operation,
            "message_id": message_id,
        }
