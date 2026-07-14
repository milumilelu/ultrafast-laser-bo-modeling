from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Protocol
import uuid

from ultrafast_domain.evolution.models import (
    EVOLVABLE_TYPES,
    RESERVED_EVOLUTION_TYPES,
    TRIGGER_TYPES,
    EvaluationRun,
    EvolvableArtifactVersion,
    EvolutionCandidate,
)


class EvolutionRepository(Protocol):
    def save_version(self, value: EvolvableArtifactVersion) -> None: ...
    def get_version(self, version_id: str) -> EvolvableArtifactVersion | None: ...
    def list_versions(self, artifact_id: str) -> list[EvolvableArtifactVersion]: ...
    def active_version(self, artifact_id: str) -> EvolvableArtifactVersion | None: ...
    def save_candidate(self, value: EvolutionCandidate) -> None: ...
    def get_candidate(self, candidate_id: str) -> EvolutionCandidate | None: ...
    def save_evaluation(self, value: EvaluationRun) -> None: ...
    def get_evaluation(self, evaluation_id: str) -> EvaluationRun | None: ...
    def append_activation(self, value: dict[str, Any]) -> None: ...
    def latest_activation(self, artifact_id: str) -> dict[str, Any] | None: ...


class InMemoryEvolutionRepository:
    def __init__(self):
        self.versions: dict[str, EvolvableArtifactVersion] = {}
        self.candidates: dict[str, EvolutionCandidate] = {}
        self.evaluations: dict[str, EvaluationRun] = {}
        self.activations: list[dict[str, Any]] = []

    def save_version(self, value: EvolvableArtifactVersion) -> None:
        existing = self.versions.get(value.artifact_version_id)
        if existing and (existing.content_hash != value.content_hash or existing.content != value.content):
            raise ValueError("artifact content is immutable")
        self.versions[value.artifact_version_id] = value

    def get_version(self, version_id: str) -> EvolvableArtifactVersion | None:
        return self.versions.get(version_id)

    def list_versions(self, artifact_id: str) -> list[EvolvableArtifactVersion]:
        return sorted((v for v in self.versions.values() if v.artifact_id == artifact_id), key=lambda v: v.version)

    def active_version(self, artifact_id: str) -> EvolvableArtifactVersion | None:
        return next((v for v in reversed(self.list_versions(artifact_id)) if v.status == "active"), None)

    def save_candidate(self, value: EvolutionCandidate) -> None:
        self.candidates[value.candidate_id] = value

    def get_candidate(self, candidate_id: str) -> EvolutionCandidate | None:
        return self.candidates.get(candidate_id)

    def save_evaluation(self, value: EvaluationRun) -> None:
        self.evaluations[value.evaluation_id] = value

    def get_evaluation(self, evaluation_id: str) -> EvaluationRun | None:
        return self.evaluations.get(evaluation_id)

    def append_activation(self, value: dict[str, Any]) -> None:
        self.activations.append(dict(value))

    def latest_activation(self, artifact_id: str) -> dict[str, Any] | None:
        return next((v for v in reversed(self.activations) if v["artifact_id"] == artifact_id), None)


Evaluator = Callable[[EvolutionCandidate, dict[str, Any]], tuple[dict[str, Any], list[str], bool]]


class EvolutionService:
    def __init__(self, repository: EvolutionRepository | None = None):
        self.repository = repository or InMemoryEvolutionRepository()

    def register_artifact_version(
        self,
        artifact_id: str,
        artifact_type: str,
        content: dict[str, Any],
        *,
        status: str = "registered",
        parent_version_id: str | None = None,
        created_from_candidate_id: str | None = None,
        source_data_version: str | None = None,
        evaluation_run_id: str | None = None,
    ) -> EvolvableArtifactVersion:
        if artifact_type not in EVOLVABLE_TYPES:
            raise ValueError(f"unsupported evolvable artifact type: {artifact_type}")
        if artifact_type in RESERVED_EVOLUTION_TYPES and status == "active":
            raise ValueError(f"reserved evolution type cannot be active: {artifact_type}")
        versions = self.repository.list_versions(artifact_id)
        if parent_version_id and self.repository.get_version(parent_version_id) is None:
            raise ValueError("parent artifact version does not exist")
        value = EvolvableArtifactVersion(
            artifact_version_id=f"artifact_version_{uuid.uuid4().hex}", artifact_id=artifact_id,
            artifact_type=artifact_type, version=len(versions) + 1, status=status,
            content_hash=_content_hash(content), content=json.loads(json.dumps(content)),
            parent_version_id=parent_version_id, created_from_candidate_id=created_from_candidate_id,
            source_data_version=source_data_version, evaluation_run_id=evaluation_run_id,
            created_at=_now(), activated_at=_now() if status == "active" else None,
        )
        if status == "active" and versions:
            raise ValueError("only the initial version may be registered active; use activation workflow")
        self.repository.save_version(value)
        return value

    def get_active_version(self, artifact_id: str) -> EvolvableArtifactVersion | None:
        return self.repository.active_version(artifact_id)

    def list_versions(self, artifact_id: str) -> list[EvolvableArtifactVersion]:
        return self.repository.list_versions(artifact_id)

    def create_evolution_candidate(
        self,
        candidate_type: str,
        target_artifact_id: str,
        proposed_content: dict[str, Any],
        reason: str,
        trigger_type: str,
        *,
        target_version_id: str | None = None,
        trigger_refs: list[str] | None = None,
        expected_benefit: dict[str, Any] | None = None,
        risk_level: str = "medium",
        created_by: str = "system",
    ) -> EvolutionCandidate:
        if candidate_type not in EVOLVABLE_TYPES:
            raise ValueError(f"unsupported candidate type: {candidate_type}")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"unsupported trigger type: {trigger_type}")
        value = EvolutionCandidate(
            candidate_id=f"evolution_candidate_{uuid.uuid4().hex}", candidate_type=candidate_type,
            target_artifact_id=target_artifact_id, target_version_id=target_version_id,
            proposed_content=json.loads(json.dumps(proposed_content)), reason=reason,
            trigger_type=trigger_type, trigger_refs=tuple(trigger_refs or ()),
            expected_benefit=dict(expected_benefit or {}), risk_level=risk_level,
            status="candidate", created_by=created_by, created_at=_now(),
        )
        self.repository.save_candidate(value)
        return value

    def prepare_candidate(self, candidate_id: str) -> EvolutionCandidate:
        return self._transition(candidate_id, {"candidate"}, "prepared")

    def run_evaluation(
        self,
        candidate_id: str,
        evaluator: Evaluator,
        *,
        dataset_version: str,
        evaluator_version: str,
        reproducibility: dict[str, Any],
    ) -> EvaluationRun:
        candidate = self._transition(candidate_id, {"prepared"}, "evaluating")
        required = {"random_seed", "code_version"}
        missing = required - set(reproducibility)
        if missing:
            raise ValueError(f"evaluation reproducibility fields missing: {sorted(missing)}")
        metrics, failures, passed = evaluator(candidate, dict(reproducibility))
        evaluation = EvaluationRun(
            evaluation_id=f"evaluation_{uuid.uuid4().hex}", candidate_id=candidate_id,
            baseline_version_id=candidate.target_version_id, dataset_version=dataset_version,
            evaluator_version=evaluator_version, metrics=metrics, failures=tuple(failures),
            passed=bool(passed), reproducibility=dict(reproducibility), created_at=_now(),
        )
        self.repository.save_evaluation(evaluation)
        candidate = replace(
            candidate,
            status="evaluation_passed" if passed else "evaluation_failed",
            evaluation_run_id=evaluation.evaluation_id,
        )
        self.repository.save_candidate(candidate)
        return evaluation

    def request_promotion(self, candidate_id: str) -> EvolutionCandidate:
        return self._transition(candidate_id, {"evaluation_passed"}, "pending_approval")

    def approve_promotion(self, candidate_id: str, approved_by: str) -> EvolutionCandidate:
        value = self._transition(candidate_id, {"pending_approval"}, "approved")
        value = replace(value, approval_by=approved_by)
        self.repository.save_candidate(value)
        return value

    def reject_promotion(self, candidate_id: str) -> EvolutionCandidate:
        return self._transition(candidate_id, {"pending_approval"}, "withdrawn")

    def activate_version(self, candidate_id: str, *, activation_reason: str, rollback_condition: str) -> EvolvableArtifactVersion:
        candidate = self._candidate(candidate_id)
        if candidate.candidate_type in RESERVED_EVOLUTION_TYPES:
            raise ValueError(
                f"reserved evolution type cannot be promoted: {candidate.candidate_type}"
            )
        if candidate.status != "approved" or not candidate.approval_by:
            raise ValueError("candidate requires explicit approval before activation")
        evaluation = self.repository.get_evaluation(candidate.evaluation_run_id or "")
        if evaluation is None or not evaluation.passed:
            raise ValueError("passed evaluation is required before activation")
        previous = self.repository.active_version(candidate.target_artifact_id)
        version = self.register_artifact_version(
            candidate.target_artifact_id, candidate.candidate_type, candidate.proposed_content,
            status="registered", parent_version_id=previous.artifact_version_id if previous else candidate.target_version_id,
            created_from_candidate_id=candidate.candidate_id, source_data_version=evaluation.dataset_version,
            evaluation_run_id=evaluation.evaluation_id,
        )
        if previous:
            self.repository.save_version(replace(previous, status="superseded", retired_at=_now()))
        active = replace(version, status="active", activated_at=_now())
        self.repository.save_version(active)
        self.repository.save_candidate(replace(candidate, status="active"))
        self.repository.append_activation(
            {
                "activation_id": f"activation_{uuid.uuid4().hex}", "artifact_id": candidate.target_artifact_id,
                "new_version_id": active.artifact_version_id,
                "previous_version_id": previous.artifact_version_id if previous else None,
                "activation_reason": activation_reason, "evaluation_id": evaluation.evaluation_id,
                "activated_at": active.activated_at, "rollback_condition": rollback_condition,
                "rollback_at": None, "rollback_reason": None,
            }
        )
        return active

    def rollback_version(self, artifact_id: str, reason: str) -> EvolvableArtifactVersion:
        activation = self.repository.latest_activation(artifact_id)
        if not activation or not activation.get("previous_version_id"):
            raise ValueError("no rollback target is available")
        current = self.repository.get_version(activation["new_version_id"])
        previous = self.repository.get_version(activation["previous_version_id"])
        if current is None or previous is None:
            raise ValueError("rollback history is incomplete")
        self.repository.save_version(replace(current, status="rolled_back", retired_at=_now()))
        restored = replace(previous, status="active", activated_at=_now(), retired_at=None)
        self.repository.save_version(restored)
        activation.update({"rollback_at": _now(), "rollback_reason": reason})
        self.repository.append_activation(activation)
        return restored

    def _candidate(self, candidate_id: str) -> EvolutionCandidate:
        value = self.repository.get_candidate(candidate_id)
        if value is None:
            raise KeyError(candidate_id)
        return value

    def _transition(self, candidate_id: str, allowed: set[str], target: str) -> EvolutionCandidate:
        value = self._candidate(candidate_id)
        if value.status not in allowed:
            raise ValueError(f"invalid evolution transition: {value.status} -> {target}")
        updated = replace(value, status=target)
        self.repository.save_candidate(updated)
        return updated


def _content_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
