from __future__ import annotations

import re
from collections import defaultdict

from ultrafast_agent.task_intake.schemas import TaskFieldCandidate, TaskSpecPatch


_SOURCE_PRIORITY = {
    "contextual_deterministic": 300,
    "llm_semantic_extraction": 200,
    "deterministic_explicit": 150,
    "legacy_regex": 50,
}


class TaskFieldCandidateResolver:
    @classmethod
    def resolve(cls, patches: list[TaskSpecPatch]) -> TaskSpecPatch:
        grouped: dict[str, list[TaskFieldCandidate]] = defaultdict(list)
        ambiguities = []
        rejected = []
        unresolved = []
        llm_attempted = False
        degraded = False
        version = patches[0].extraction_version if patches else "hybrid-slot-v1"
        for patch in patches:
            for candidate in patch.updates:
                grouped[candidate.field_name].append(candidate)
            ambiguities.extend(patch.ambiguities)
            rejected.extend(patch.rejected_candidates)
            unresolved.extend(patch.unresolved_fields)
            llm_attempted = llm_attempted or patch.llm_attempted
            degraded = degraded or patch.degraded

        resolved = []
        for field, candidates in grouped.items():
            corrections = [item for item in candidates if item.operation in {"correct", "clear"}]
            pool = corrections or candidates
            keys = {cls._semantic_key(item.raw_value) for item in pool}
            if len(keys) > 1:
                ambiguities.append(
                    {
                        "field_name": field,
                        "reason": "candidate_conflict",
                        "evidence": [item.evidence for item in pool],
                    }
                )
                continue
            resolved.append(max(pool, key=cls._priority))
        covered = {item.field_name for item in resolved}
        return TaskSpecPatch(
            updates=resolved,
            unresolved_fields=list(dict.fromkeys(field for field in unresolved if field not in covered)),
            ambiguities=ambiguities,
            rejected_candidates=rejected,
            extraction_version=version,
            llm_attempted=llm_attempted,
            degraded=degraded,
        )

    @staticmethod
    def _priority(candidate: TaskFieldCandidate) -> tuple[int, float]:
        correction = 1000 if candidate.operation in {"correct", "clear"} else 0
        return correction + _SOURCE_PRIORITY.get(candidate.extraction_source, 0), candidate.confidence

    @staticmethod
    def _semantic_key(value: object) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        text = re.sub(r"\s+", "", str(value)).lower()
        aliases = {"允许": "true", "可以": "true", "不允许": "false", "不可以": "false"}
        return aliases.get(text, text)

