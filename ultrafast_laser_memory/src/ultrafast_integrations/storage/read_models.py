from __future__ import annotations

import json

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def _query(sql: str, parameters: tuple = ()) -> list[dict]:
    init_database()
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def list_artifacts(limit: int = 50) -> list[dict]:
    return _query("SELECT * FROM raw_artifact ORDER BY imported_at DESC LIMIT ?", (limit,))


def list_runs(limit: int = 50) -> list[dict]:
    return _query("SELECT * FROM process_run ORDER BY start_time DESC LIMIT ?", (limit,))


def list_rag_documents() -> list[dict]:
    return _query("SELECT * FROM rag_document ORDER BY created_at DESC")


def find_candidate_rag_documents(candidate_id: str) -> list[str]:
    return [
        row["rag_doc_id"]
        for row in _query("SELECT rag_doc_id FROM rag_document WHERE candidate_id = ?", (candidate_id,))
    ]


def get_session_bootstrap_read_model(
    pending_review_ids: list[str], accepted_rag_doc_ids: list[str]
) -> dict[str, list[dict]]:
    pending: list[dict] = []
    accepted: list[dict] = []
    for review_id in pending_review_ids:
        pending.extend(
            _query("SELECT * FROM knowledge_review_task WHERE review_id = ?", (review_id,))
        )
    for rag_doc_id in accepted_rag_doc_ids:
        accepted.extend(_query("SELECT * FROM rag_document WHERE rag_doc_id = ?", (rag_doc_id,)))
    return {"pending_review_tasks": pending, "accepted_rag_documents": accepted}


def list_bo_training_samples() -> list[dict]:
    rows = _query("SELECT * FROM bo_training_sample WHERE valid_for_training=1 ORDER BY added_at")
    for row in rows:
        row["x_parameters"] = json.loads(row.pop("x_parameters_json") or "{}")
        row["y_metrics"] = json.loads(row.pop("y_metrics_json") or "{}")
    return rows


def find_similar_process_cases(task_spec: dict, limit: int = 5) -> list[dict]:
    material = task_spec.get("material")
    process_type = task_spec.get("process_type")
    sql = """
        SELECT t.task_id, t.material, t.material_grade, t.component_type,
               p.process_type, r.run_id, r.run_status
        FROM process_task t
        JOIN process_run r ON r.task_id=t.task_id
        LEFT JOIN process_recipe p ON p.recipe_id=r.recipe_id
        WHERE r.run_status='completed'
          AND (? IS NULL OR t.material=?)
          AND (? IS NULL OR p.process_type=?)
        ORDER BY r.end_time DESC
        LIMIT ?
    """
    return _query(sql, (material, material, process_type, process_type, limit))
