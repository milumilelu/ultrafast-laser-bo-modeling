from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


EVOLVABLE_TYPES = frozenset(
    {
        "bo_model", "bo_acquisition_strategy", "router_policy", "skill_definition",
        "prompt_template", "rag_query_strategy", "workflow_policy",
        "process_prior_candidate", "validated_rule_candidate",
    }
)

FORBIDDEN_AUTOMATIC_ACTIVATION = frozenset(
    {"equipment_hard_boundary", "database_schema", "production_code", "safety_rule", "tool", "validated_rule"}
)

TRIGGER_TYPES = frozenset(
    {
        "performance_regression", "repeated_failure", "user_feedback", "new_experiment_data",
        "knowledge_conflict", "manual_proposal", "llm_proposal",
    }
)


@dataclass(frozen=True, slots=True)
class EvolvableArtifactVersion:
    artifact_version_id: str
    artifact_id: str
    artifact_type: str
    version: int
    status: str
    content_hash: str
    content: dict[str, Any]
    parent_version_id: str | None = None
    created_from_candidate_id: str | None = None
    source_data_version: str | None = None
    evaluation_run_id: str | None = None
    created_at: str | None = None
    activated_at: str | None = None
    retired_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    candidate_id: str
    candidate_type: str
    target_artifact_id: str
    target_version_id: str | None
    proposed_content: dict[str, Any]
    reason: str
    trigger_type: str
    trigger_refs: tuple[str, ...] = ()
    expected_benefit: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    status: str = "candidate"
    created_by: str = "system"
    created_at: str | None = None
    evaluation_run_id: str | None = None
    approval_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trigger_refs"] = list(self.trigger_refs)
        return value


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    evaluation_id: str
    candidate_id: str
    baseline_version_id: str | None
    dataset_version: str
    evaluator_version: str
    metrics: dict[str, Any]
    failures: tuple[str, ...]
    passed: bool
    reproducibility: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["failures"] = list(self.failures)
        return value

