from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class BODatasetVersion:
    dataset_version_id: str
    content_hash: str
    sample_ids: tuple[str, ...]
    slice_scope: dict[str, Any]
    feature_schema_version: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self); value["sample_ids"] = list(self.sample_ids); return value


@dataclass(frozen=True, slots=True)
class BOModelArtifact:
    model_version_id: str
    artifact_path: str | None
    model_type: str
    hyperparameters: dict[str, Any]
    training_dataset_version: str
    feature_schema_version: str
    objective_version: str
    code_version: str
    random_seed: int
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class BOEvaluationRun:
    evaluation_id: str
    model_version_id: str
    baseline_model_version_id: str | None
    dataset_version: str
    split_strategy: str
    metrics: dict[str, Any]
    failures: tuple[str, ...]
    passed: bool
    created_at: str


class BOModelRegistry:
    def __init__(self):
        self.datasets: dict[str, BODatasetVersion] = {}
        self.models: dict[str, BOModelArtifact] = {}
        self.evaluations: dict[str, BOEvaluationRun] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self._active: dict[str, str] = {}
        self._previous: dict[str, str] = {}

    def register_dataset(self, sample_ids: list[str], slice_scope: dict[str, Any], feature_schema_version: str) -> BODatasetVersion:
        canonical = {"sample_ids": sorted(sample_ids), "slice_scope": slice_scope, "feature_schema_version": feature_schema_version}
        content_hash = _hash(canonical)
        version_id = f"bo_dataset_{content_hash[:16]}"
        value = BODatasetVersion(version_id, content_hash, tuple(sorted(sample_ids)), dict(slice_scope), feature_schema_version, _now())
        self.datasets.setdefault(version_id, value)
        return self.datasets[version_id]

    def register_model(self, **values: Any) -> BOModelArtifact:
        value = BOModelArtifact(
            model_version_id=values.get("model_version_id") or f"bo_model_{uuid.uuid4().hex}",
            artifact_path=values.get("artifact_path"), model_type=values.get("model_type", "gp_matern_ard"),
            hyperparameters=dict(values.get("hyperparameters") or {}),
            training_dataset_version=values["training_dataset_version"],
            feature_schema_version=values.get("feature_schema_version", "1.0"),
            objective_version=values.get("objective_version", "1.0"),
            code_version=values.get("code_version", "unknown"), random_seed=int(values.get("random_seed", 42)),
            status=values.get("status", "candidate"), created_at=_now(),
        )
        self.models[value.model_version_id] = value
        return value

    def record_evaluation(self, model_version_id: str, dataset_version: str, metrics: dict[str, Any], *, failures: list[str] | None = None, split_strategy: str = "group_kfold", baseline_model_version_id: str | None = None, passed: bool = False) -> BOEvaluationRun:
        value = BOEvaluationRun(
            f"bo_evaluation_{uuid.uuid4().hex}", model_version_id, baseline_model_version_id,
            dataset_version, split_strategy, dict(metrics), tuple(failures or ()), bool(passed), _now(),
        )
        self.evaluations[value.evaluation_id] = value
        return value

    def activate(self, artifact_id: str, model_version_id: str, evaluation_id: str, approved_by: str) -> BOModelArtifact:
        model = self.models[model_version_id]
        evaluation = self.evaluations[evaluation_id]
        if evaluation.model_version_id != model_version_id or not evaluation.passed:
            raise ValueError("a passed matching evaluation is required")
        if not approved_by:
            raise ValueError("explicit approval is required")
        previous = self._active.get(artifact_id)
        if previous:
            self._previous[artifact_id] = previous
        self._active[artifact_id] = model_version_id
        active = BOModelArtifact(**{**asdict(model), "status": "active"})
        self.models[model_version_id] = active
        return active

    def rollback(self, artifact_id: str) -> BOModelArtifact:
        previous = self._previous.get(artifact_id)
        if not previous:
            raise ValueError("no rollback model version")
        current = self._active[artifact_id]
        self.models[current] = BOModelArtifact(**{**asdict(self.models[current]), "status": "rolled_back"})
        restored = BOModelArtifact(**{**asdict(self.models[previous]), "status": "active"})
        self.models[previous] = restored
        self._active[artifact_id] = previous
        return restored

    def record_run(self, run: dict[str, Any]) -> None:
        required = {"bo_run_id", "training_sample_ids", "dataset_version", "model_version", "feature_schema_version", "objective_version", "acquisition_version", "random_seed", "code_commit", "equipment_profile_version", "approved_prior_versions", "result"}
        missing = required - set(run)
        if missing:
            raise ValueError(f"BO run trace fields missing: {sorted(missing)}")
        self.runs[run["bo_run_id"]] = json.loads(json.dumps(run))

    def replay_bo_run(self, bo_run_id: str) -> dict[str, Any]:
        if bo_run_id not in self.runs:
            raise KeyError(bo_run_id)
        return json.loads(json.dumps(self.runs[bo_run_id]))
