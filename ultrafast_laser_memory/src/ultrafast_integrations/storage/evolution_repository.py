from __future__ import annotations

import json
from typing import Any

from ultrafast_domain.evolution.models import EvaluationRun, EvolvableArtifactVersion, EvolutionCandidate
from ultrafast_memory.db.session import get_connection


class SQLiteEvolutionRepository:
    """Persistent implementation of the evolution control-plane repository."""

    def save_version(self, value: EvolvableArtifactVersion) -> None:
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT content_hash, content_json FROM evolvable_artifact_version WHERE artifact_version_id=?",
                (value.artifact_version_id,),
            ).fetchone()
            payload = _dump(value.content)
            if existing and (existing["content_hash"] != value.content_hash or existing["content_json"] != payload):
                raise ValueError("artifact content is immutable")
            conn.execute(
                """INSERT INTO evolvable_artifact_version VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(artifact_version_id) DO UPDATE SET
                   status=excluded.status, activated_at=excluded.activated_at, retired_at=excluded.retired_at""",
                (
                    value.artifact_version_id, value.artifact_id, value.artifact_type, value.version,
                    value.status, value.content_hash, payload, value.parent_version_id,
                    value.created_from_candidate_id, value.source_data_version, value.evaluation_run_id,
                    value.created_at, value.activated_at, value.retired_at,
                ),
            )
            conn.commit()

    def get_version(self, version_id: str) -> EvolvableArtifactVersion | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM evolvable_artifact_version WHERE artifact_version_id=?", (version_id,)
            ).fetchone()
        return _version(row) if row else None

    def list_versions(self, artifact_id: str) -> list[EvolvableArtifactVersion]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM evolvable_artifact_version WHERE artifact_id=? ORDER BY version", (artifact_id,)
            ).fetchall()
        return [_version(row) for row in rows]

    def active_version(self, artifact_id: str) -> EvolvableArtifactVersion | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM evolvable_artifact_version WHERE artifact_id=? AND status='active' ORDER BY version DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        return _version(row) if row else None

    def save_candidate(self, value: EvolutionCandidate) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO evolution_candidate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(candidate_id) DO UPDATE SET status=excluded.status,
                   evaluation_run_id=excluded.evaluation_run_id, approval_by=excluded.approval_by""",
                (
                    value.candidate_id, value.candidate_type, value.target_artifact_id, value.target_version_id,
                    _dump(value.proposed_content), value.reason, value.trigger_type, _dump(list(value.trigger_refs)),
                    _dump(value.expected_benefit), value.risk_level, value.status, value.created_by,
                    value.created_at, value.evaluation_run_id, value.approval_by,
                ),
            )
            conn.commit()

    def get_candidate(self, candidate_id: str) -> EvolutionCandidate | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM evolution_candidate WHERE candidate_id=?", (candidate_id,)).fetchone()
        if not row:
            return None
        return EvolutionCandidate(
            candidate_id=row["candidate_id"], candidate_type=row["candidate_type"],
            target_artifact_id=row["target_artifact_id"], target_version_id=row["target_version_id"],
            proposed_content=_load(row["proposed_content_json"], {}), reason=row["reason"],
            trigger_type=row["trigger_type"], trigger_refs=tuple(_load(row["trigger_refs_json"], [])),
            expected_benefit=_load(row["expected_benefit_json"], {}), risk_level=row["risk_level"],
            status=row["status"], created_by=row["created_by"], created_at=row["created_at"],
            evaluation_run_id=row["evaluation_run_id"], approval_by=row["approval_by"],
        )

    def save_evaluation(self, value: EvaluationRun) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO evolution_evaluation_run VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    value.evaluation_id, value.candidate_id, value.baseline_version_id, value.dataset_version,
                    value.evaluator_version, _dump(value.metrics), _dump(list(value.failures)), int(value.passed),
                    _dump(value.reproducibility), value.created_at,
                ),
            )
            conn.commit()

    def get_evaluation(self, evaluation_id: str) -> EvaluationRun | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM evolution_evaluation_run WHERE evaluation_id=?", (evaluation_id,)
            ).fetchone()
        if not row:
            return None
        return EvaluationRun(
            evaluation_id=row["evaluation_id"], candidate_id=row["candidate_id"],
            baseline_version_id=row["baseline_version_id"], dataset_version=row["dataset_version"],
            evaluator_version=row["evaluator_version"], metrics=_load(row["metrics_json"], {}),
            failures=tuple(_load(row["failures_json"], [])), passed=bool(row["passed"]),
            reproducibility=_load(row["reproducibility_json"], {}), created_at=row["created_at"],
        )

    def append_activation(self, value: dict[str, Any]) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO evolution_activation VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(activation_id) DO UPDATE SET rollback_at=excluded.rollback_at,
                   rollback_reason=excluded.rollback_reason""",
                (
                    value["activation_id"], value["artifact_id"], value["new_version_id"],
                    value.get("previous_version_id"), value["activation_reason"], value["evaluation_id"],
                    value["activated_at"], value.get("rollback_condition"), value.get("rollback_at"),
                    value.get("rollback_reason"),
                ),
            )
            conn.commit()

    def latest_activation(self, artifact_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM evolution_activation WHERE artifact_id=? ORDER BY activated_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        return dict(row) if row else None


def _version(row: Any) -> EvolvableArtifactVersion:
    return EvolvableArtifactVersion(
        artifact_version_id=row["artifact_version_id"], artifact_id=row["artifact_id"],
        artifact_type=row["artifact_type"], version=int(row["version"]), status=row["status"],
        content_hash=row["content_hash"], content=_load(row["content_json"], {}),
        parent_version_id=row["parent_version_id"], created_from_candidate_id=row["created_from_candidate_id"],
        source_data_version=row["source_data_version"], evaluation_run_id=row["evaluation_run_id"],
        created_at=row["created_at"], activated_at=row["activated_at"], retired_at=row["retired_at"],
    )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default
