from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class ProcessWorkflowRepository:
    """SQLite source of truth for the formal-process and closure records."""

    def __init__(self) -> None:
        init_database()

    def save_plan(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO formal_process_plan VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (record["plan_id"], record["task_id"], record.get("trial_result_id"),
                 record.get("parameter_recommendation_id"), record["equipment_revision"],
                 _dump(record.get("approved_window") or {}), _dump(record.get("toolpath") or {}),
                 _dump(record.get("monitoring_plan") or {}), _dump(record.get("stop_conditions") or []),
                 record["release_status"], record["created_at"]),
            )
            conn.commit()
        return record

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM formal_process_plan WHERE plan_id = ?", (plan_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        for field in ("approved_window", "toolpath", "monitoring_plan", "stop_conditions"):
            value[field] = _load(value.pop(field + "_json"), {} if field != "stop_conditions" else [])
        return value

    def set_plan_status(self, plan_id: str, status: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE formal_process_plan SET release_status = ? WHERE plan_id = ?", (status, plan_id))
            conn.commit()

    def save_execution(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO formal_process_execution VALUES (?,?,?,?,?,?,?,?)",
                (record["execution_id"], record["plan_id"], _dump(record.get("actual_parameters") or {}),
                 _dump(record.get("actual_path") or {}), _dump(record.get("runtime_log") or {}),
                 record["started_at"], record.get("finished_at"), record["status"]),
            )
            conn.commit()
        return record

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM formal_process_execution WHERE execution_id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value["actual_parameters"] = _load(value.pop("actual_parameters_json"), {})
        value["actual_path"] = _load(value.pop("actual_path_json"), {})
        value["runtime_log"] = _load(value.pop("runtime_log_json"), {})
        return value

    def update_execution(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute(
                "UPDATE formal_process_execution SET runtime_log_json=?, finished_at=?, status=? WHERE execution_id=?",
                (_dump(record.get("runtime_log") or {}), record.get("finished_at"), record["status"], record["execution_id"]),
            )
            conn.commit()
        return record

    def save_checkpoint(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute("INSERT INTO process_checkpoint VALUES (?,?,?,?,?,?,?)", (
                record["checkpoint_id"], record["execution_id"], record["checkpoint_type"],
                record.get("progress_percent"), _dump(record.get("observation") or {}),
                record["decision"], record["created_at"]))
            conn.commit()
        return record

    def save_inspection(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute("INSERT INTO inspection_record VALUES (?,?,?,?,?,?,?,?)", (
                record["inspection_id"], record["execution_id"], _dump(record.get("measurement_plan") or {}),
                _dump(record.get("measurements") or {}), _dump(record.get("defects") or []),
                _dump(record.get("files") or []), record["completeness_status"], record["created_at"]))
            conn.commit()
        return record

    def get_inspection(self, inspection_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM inspection_record WHERE inspection_id = ?", (inspection_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        for field, default in (("measurement_plan", {}), ("measurements", {}), ("defects", []), ("files", [])):
            value[field] = _load(value.pop(field + "_json"), default)
        return value

    def save_quality_decision(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute("INSERT INTO quality_decision VALUES (?,?,?,?,?,?,?,?,?)", (
                record["quality_decision_id"], record["inspection_id"], record["decision"],
                _dump(record.get("passed_metrics") or []), _dump(record.get("failed_metrics") or []),
                _dump(record.get("missing_metrics") or []), _dump(record.get("basis") or {}),
                record.get("reviewer_comment"), record["created_at"]))
            conn.commit()
        return record

    def save_experiment(self, record: dict[str, Any]) -> dict[str, Any]:
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO experiment_record VALUES (?,?,?,?,?,?,?)", (
                record["experiment_id"], record["task_id"], record["execution_id"], _dump(record),
                record.get("validation_status", "pending"), int(bool(record.get("bo_eligible"))), record["created_at"]))
            conn.commit()
        return record

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute("SELECT record_json FROM experiment_record WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return _load(row[0], {}) if row else None

    def set_campaign_status(self, campaign_id: str, status: str, updated_at: str) -> bool:
        with get_connection() as conn:
            cursor = conn.execute("UPDATE optimization_campaign SET status=?, updated_at=? WHERE campaign_id=?",
                                  (status, updated_at, campaign_id))
            conn.commit()
        return cursor.rowcount > 0

    def approve_rework(self, campaign_id: str, updated_at: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT task_id FROM optimization_campaign WHERE campaign_id=? AND campaign_type='rework_campaign'",
                (campaign_id,)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE optimization_campaign SET status='approved', updated_at=? WHERE campaign_id=?",
                         (updated_at, campaign_id))
            conn.commit()
        return {"rework_plan_id": campaign_id, "task_id": row[0], "status": "approved"}
