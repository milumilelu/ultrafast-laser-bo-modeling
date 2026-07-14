from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ultrafast_agent.task_intake.extraction_service import TaskFieldExtractionService
from ultrafast_agent.task_intake.merge_service import TaskSpecMergeService
from ultrafast_agent.task_intake.missing_field_service import MissingFieldEvaluator
from ultrafast_agent.task_intake.normalizer import TaskFieldNormalizer
from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_agent.task_intake.validator import TaskSpecPatchValidator


CRITICAL_FIELDS = frozenset({"process_type", "material", "thickness_mm", "layer_cut_allowed"})


@dataclass(frozen=True, slots=True)
class ReplayCase:
    case_id: str
    tags: tuple[str, ...]
    turns: tuple[str, ...]
    structured_outputs: tuple[dict[str, Any], ...]
    initial_task_spec: dict[str, Any]
    expected_task_spec: dict[str, Any]
    expected_missing_fields: tuple[str, ...]
    expected_business_state: str
    invariants: tuple[str, ...]


class FixtureStructuredClient:
    provider = "fixture"
    model = "task-intake-replay-v1"

    def __init__(self, outputs: tuple[dict[str, Any], ...]):
        self.outputs = list(outputs)
        self.index = 0

    def chat(self, messages: list[dict[str, str]], **_: Any) -> dict[str, str]:
        if self.index >= len(self.outputs):
            raise AssertionError("fixture output missing for LLM turn")
        value = self.outputs[self.index]
        self.index += 1
        return {"content": json.dumps(value, ensure_ascii=False)}


def load_replay_cases(path: str | Path) -> list[ReplayCase]:
    cases: list[ReplayCase] = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        family = json.loads(raw_line)
        variants = family.get("variants") or [family["turns"]]
        for index, variant in enumerate(variants, start=1):
            turns = [variant] if isinstance(variant, str) else variant
            suffix = f"_{index:02d}" if len(variants) > 1 else ""
            expected = family["expected"]
            cases.append(ReplayCase(
                case_id=f"{family['case_id']}{suffix}",
                tags=tuple(family.get("tags") or ()),
                turns=tuple(turns),
                structured_outputs=tuple(family.get("structured_outputs") or ()),
                initial_task_spec=deepcopy(family.get("initial_task_spec") or {}),
                expected_task_spec=deepcopy(expected["task_spec"]),
                expected_missing_fields=tuple(expected.get("missing_fields") or ()),
                expected_business_state=expected.get("business_state", "INTAKE"),
                invariants=tuple(family.get("invariants") or ()),
            ))
    return cases


def run_replay_case(case: ReplayCase, client: Any | None = None) -> dict[str, Any]:
    task = deepcopy(case.initial_task_spec)
    provenance: dict[str, dict[str, Any]] = {}
    revisions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    llm = client or FixtureStructuredClient(case.structured_outputs)
    previous_questions: list[dict[str, Any]] = []
    for turn_number, message in enumerate(case.turns, start=1):
        pending = MissingFieldEvaluator.evaluate(task)
        context = ClarificationContext(
            workflow_type="complex_process_task",
            stage="REQUIREMENTS_PENDING",
            clarification_round=turn_number,
            pending_fields=pending,
            ordered_fields=pending,
            previous_questions=previous_questions,
        )
        patch = TaskFieldExtractionService(llm).extract(message, task, context)
        patch = TaskFieldNormalizer.normalize(patch)
        patch = TaskSpecPatchValidator.validate(patch, task, context, user_message=message)
        merged = TaskSpecMergeService.merge(
            task,
            patch,
            current_provenance=provenance,
            revision_history=revisions,
            message_id=f"{case.case_id}:{turn_number}",
            context=context,
        )
        task, provenance, revisions = (
            merged.task_spec,
            merged.field_provenance,
            merged.revision_history,
        )
        conflicts.extend(merged.conflicts)
        rejected.extend(patch.rejected_candidates)
        previous_questions = [
            {"field": field, "question": f"请补充 {field}"}
            for field in MissingFieldEvaluator.evaluate(task)
        ]
    missing = MissingFieldEvaluator.evaluate(task)
    business_state = "TRIAL" if not missing else "INTAKE"
    return {
        "case_id": case.case_id,
        "tags": list(case.tags),
        "task_spec": task,
        "missing_fields": missing,
        "business_state": business_state,
        "conflicts": conflicts,
        "rejected_candidates": rejected,
        "revision_history": revisions,
        "passed": (
            task == case.expected_task_spec
            and missing == list(case.expected_missing_fields)
            and business_state == case.expected_business_state
        ),
    }


def evaluate_replay(cases: list[ReplayCase], client_factory: Any | None = None) -> dict[str, Any]:
    results = [
        run_replay_case(case, client_factory(case) if client_factory else None)
        for case in cases
    ]
    expected_pairs = 0
    correct_pairs = 0
    actual_pairs = 0
    hallucinated = 0
    critical_total = 0
    critical_correct = 0
    unintended_overwrites = 0
    progression_correct = 0
    schema_valid = 0
    for case, result in zip(cases, results, strict=True):
        expected_pairs += len(case.expected_task_spec)
        actual_pairs += len(result["task_spec"])
        correct_pairs += sum(
            result["task_spec"].get(field) == value
            for field, value in case.expected_task_spec.items()
        )
        hallucinated += len(set(result["task_spec"]) - set(case.expected_task_spec))
        critical = CRITICAL_FIELDS & set(case.expected_task_spec)
        critical_total += len(critical)
        critical_correct += sum(
            result["task_spec"].get(field) == case.expected_task_spec[field]
            for field in critical
        )
        explicitly_corrected = {item["field_name"] for item in result["revision_history"]}
        unintended_overwrites += sum(
            field not in explicitly_corrected and result["task_spec"].get(field) != value
            for field, value in case.initial_task_spec.items()
        )
        progression_correct += result["business_state"] == case.expected_business_state
        schema_valid += not any(
            item.get("reason", "").startswith("normalization_failed")
            for item in result["rejected_candidates"]
        )
    count = max(1, len(cases))
    return {
        "case_count": len(cases),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "field_precision": round(correct_pairs / max(1, actual_pairs), 6),
        "field_recall": round(correct_pairs / max(1, expected_pairs), 6),
        "critical_field_accuracy": round(critical_correct / max(1, critical_total), 6),
        "schema_valid_rate": round(schema_valid / count, 6),
        "hallucinated_field_rate": round(hallucinated / max(1, actual_pairs), 6),
        "existing_field_overwrite_rate": round(unintended_overwrites / count, 6),
        "workflow_progression_accuracy": round(progression_correct / count, 6),
        "results": results,
    }
