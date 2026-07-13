from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import uuid

from ultrafast_domain.process.recommendation import ProcessRecommendation
from ultrafast_memory.db.session import get_connection


class ProcessRecommendationRepository:
    """SQLite persistence adapter; application policy stays outside integrations."""

    def next_iteration(self, task_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(iteration_number),0)+1 FROM process_recommendation WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return int(row[0])

    def save(self, value: ProcessRecommendation) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO process_recommendation VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    value.recommendation_id, value.task_id, value.workflow_id,
                    value.iteration_number, value.parent_recommendation_id, value.status,
                    json.dumps(value.to_dict(), ensure_ascii=False), value.created_at, value.expires_at,
                ),
            )
            conn.commit()

    def get(self, recommendation_id: str) -> dict[str, Any]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT recommendation_json FROM process_recommendation WHERE recommendation_id=?",
                (recommendation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(recommendation_id)
        return json.loads(row[0])

    def save_cam_export(self, export_id: str, recommendation_id: str, payload: dict[str, Any], created_at: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO cam_export VALUES (?,?,?,?,?,?)",
                (export_id, recommendation_id, "generic_json", "1.0", json.dumps(payload, ensure_ascii=False), created_at),
            )
            conn.commit()

    def save_feedback_candidate(
        self,
        feedback_id: str,
        recommendation_id: str,
        feedback: dict[str, Any],
        candidate_id: str,
        candidate: dict[str, Any],
        eligibility: dict[str, Any],
        status: str,
        created_at: str,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO process_feedback VALUES (?,?,?,?,?)",
                (feedback_id, recommendation_id, json.dumps(feedback, ensure_ascii=False), "received", created_at),
            )
            conn.execute(
                "INSERT INTO bo_training_sample_candidate VALUES (?,?,?,?,?,?,?)",
                (
                    candidate_id, recommendation_id, feedback_id,
                    json.dumps(candidate, ensure_ascii=False), json.dumps(eligibility, ensure_ascii=False),
                    status, created_at,
                ),
            )
            conn.commit()

    def get_training_candidate(self, candidate_id: str) -> dict[str, Any]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM bo_training_sample_candidate WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return {
            **dict(row), "candidate": json.loads(row["candidate_json"]),
            "eligibility_report": json.loads(row["eligibility_report_json"]),
        }

    def approve_training_candidate(self, candidate_id: str, approved_by: str) -> dict[str, str]:
        if not approved_by:
            raise ValueError("approved_by is required")
        approval_id, sample_id = f"bo_approval_{uuid.uuid4().hex}", f"bo_sample_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM bo_training_sample_candidate WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            existing = conn.execute(
                "SELECT approval_id, sample_id, approved_by, approved_at FROM approved_bo_training_sample WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if existing:
                conn.commit()
                return dict(existing)
            if row["status"] != "eligible_pending_approval":
                raise ValueError("only eligible_pending_approval candidates can be approved")
            conn.execute(
                "INSERT INTO approved_bo_training_sample VALUES (?,?,?,?,?)",
                (approval_id, candidate_id, sample_id, approved_by, now),
            )
            conn.execute(
                "UPDATE bo_training_sample_candidate SET status='approved' WHERE candidate_id=?", (candidate_id,)
            )
            conn.commit()
        return {"approval_id": approval_id, "sample_id": sample_id, "approved_by": approved_by, "approved_at": now}

    def save_dataset_version(self, value: dict[str, Any]) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO bo_dataset_version VALUES (?,?,?,?,?,?)",
                (
                    value["dataset_version_id"], value["content_hash"],
                    json.dumps(value["sample_ids"], ensure_ascii=False),
                    json.dumps(value["slice_scope"], ensure_ascii=False, sort_keys=True),
                    value["feature_schema_version"], value["created_at"],
                ),
            )
            conn.commit()
