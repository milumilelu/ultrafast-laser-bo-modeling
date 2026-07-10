from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_shared.db.unit_of_work import UnitOfWork


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class TrialRepository:
    def create_plan(self, draft: dict[str, Any]) -> dict[str, Any]:
        init_database()
        plan_id = _id("trial-plan")
        now = _now()
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO trial_plan VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    plan_id,
                    draft["task_id"],
                    draft["trial_mode"],
                    _json(draft["representative_geometry"]),
                    _json(draft["parameter_matrix"]),
                    _json(draft["measurement_plan"]),
                    _json(draft["acceptance_criteria"]),
                    _json(draft["stop_conditions"]),
                    draft.get("status", "draft"),
                    now,
                    now,
                ),
            )
            uow.commit()
        return self.get_plan(plan_id)

    def get_plan(self, trial_plan_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_plan WHERE trial_plan_id = ?", (trial_plan_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"trial plan not found: {trial_plan_id}")
        result = dict(row)
        for key in (
            "representative_geometry_json",
            "parameter_matrix_json",
            "measurement_plan_json",
            "acceptance_criteria_json",
            "stop_conditions_json",
        ):
            result[key.removesuffix("_json")] = _loads(result.pop(key), [] if key in {"parameter_matrix_json", "acceptance_criteria_json", "stop_conditions_json"} else {})
        return result

    def start_execution(
        self,
        trial_plan_id: str,
        equipment_revision: str,
        actual_parameters: dict[str, Any],
        actual_path: dict[str, Any],
        monitoring_summary: dict[str, Any],
    ) -> dict[str, Any]:
        plan = self.get_plan(trial_plan_id)
        if plan["status"] == "skipped":
            raise ValueError("cannot execute a skipped trial plan")
        execution_id = _id("trial-execution")
        now = _now()
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO trial_execution VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    execution_id,
                    trial_plan_id,
                    equipment_revision,
                    _json(actual_parameters),
                    _json(actual_path),
                    _json(monitoring_summary),
                    now,
                    None,
                    "running",
                ),
            )
            uow.connection.execute(
                "UPDATE trial_plan SET status='running', updated_at=? WHERE trial_plan_id=?",
                (now, trial_plan_id),
            )
            uow.commit()
        return self.get_execution(execution_id)

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_execution WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"trial execution not found: {execution_id}")
        result = dict(row)
        for key in ("actual_parameters_json", "actual_path_json", "monitoring_summary_json"):
            result[key.removesuffix("_json")] = _loads(result.pop(key), {})
        return result

    def create_result(
        self,
        execution_id: str,
        measurements: dict[str, Any],
        defects: list[dict[str, Any]] | dict[str, Any],
    ) -> dict[str, Any]:
        execution = self.get_execution(execution_id)
        result_id = _id("trial-result")
        now = _now()
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO trial_result VALUES (?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    execution_id,
                    _json(measurements),
                    _json(defects),
                    "pending_evaluation",
                    None,
                    None,
                    now,
                ),
            )
            uow.connection.execute(
                "UPDATE trial_execution SET status='completed', finished_at=? WHERE execution_id=?",
                (now, execution_id),
            )
            uow.connection.execute(
                "UPDATE trial_plan SET status='evaluating', updated_at=? WHERE trial_plan_id=?",
                (now, execution["trial_plan_id"]),
            )
            uow.commit()
        return self.get_result(result_id)

    def get_result(self, result_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_result WHERE result_id = ?", (result_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"trial result not found: {result_id}")
        result = dict(row)
        result["measurements"] = _loads(result.pop("measurements_json"), {})
        result["defects"] = _loads(result.pop("defects_json"), [])
        return result

    def evaluate_result(
        self,
        result_id: str,
        evaluation: dict[str, Any],
        reviewer_comment: str | None,
        formal_process_unlocked: bool,
    ) -> dict[str, Any]:
        result = self.get_result(result_id)
        execution = self.get_execution(result["execution_id"])
        plan = self.get_plan(execution["trial_plan_id"])
        now = _now()
        formal_id = _id("formal-decision")
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE trial_result SET quality_status=?, decision=?, reviewer_comment=? WHERE result_id=?",
                (
                    evaluation["quality_status"],
                    evaluation["decision"],
                    reviewer_comment,
                    result_id,
                ),
            )
            uow.connection.execute(
                "UPDATE trial_plan SET status=?, updated_at=? WHERE trial_plan_id=?",
                (
                    "passed" if formal_process_unlocked else evaluation["decision"],
                    now,
                    plan["trial_plan_id"],
                ),
            )
            uow.connection.execute(
                "INSERT INTO formal_process_decision VALUES (?,?,?,?,?,?,?)",
                (
                    formal_id,
                    plan["task_id"],
                    result_id,
                    evaluation["decision"],
                    int(formal_process_unlocked),
                    "; ".join(evaluation["failures"] + evaluation["missing_measurements"]) or "trial acceptance criteria satisfied",
                    now,
                ),
            )
            uow.commit()
        return {
            **self.get_result(result_id),
            "evaluation": evaluation,
            "formal_process_decision": {
                "formal_decision_id": formal_id,
                "task_id": plan["task_id"],
                "unlocked": formal_process_unlocked,
                "decision": evaluation["decision"],
            },
        }
