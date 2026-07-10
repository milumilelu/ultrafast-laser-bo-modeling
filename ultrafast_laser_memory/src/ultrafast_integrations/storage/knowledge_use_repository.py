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
    return json.loads(value) if value else default


class KnowledgeUseRepository:
    def create_decision(
        self,
        *,
        session_id: str | None,
        task_id: str,
        intended_use: str,
        evidence_ids: list[str],
        proposed_usage: dict[str, Any],
        risk_level: str,
    ) -> dict[str, Any]:
        init_database()
        decision_id = _id("knowledge-decision")
        now = _now()
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO knowledge_usage_decision VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    decision_id,
                    session_id,
                    task_id,
                    intended_use,
                    _json(evidence_ids[:5]),
                    _json(proposed_usage),
                    risk_level,
                    "pending",
                    now,
                    None,
                ),
            )
            uow.commit()
        return self.get_decision(decision_id)

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_usage_decision WHERE decision_id=?", (decision_id,)
            ).fetchone()
            approvals = connection.execute(
                "SELECT * FROM knowledge_usage_approval WHERE decision_id=? ORDER BY created_at",
                (decision_id,),
            ).fetchall()
        if not row:
            raise ValueError(f"knowledge usage decision not found: {decision_id}")
        result = dict(row)
        result["evidence_ids"] = _loads(result.pop("evidence_ids_json"), [])
        result["proposed_usage"] = _loads(result.pop("proposed_usage_json"), {})
        result["approvals"] = [self._approval_dict(dict(item)) for item in approvals]
        return result

    def find_task_decision(self, task_id: str) -> dict[str, Any] | None:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT decision_id FROM knowledge_usage_decision WHERE task_id=? ORDER BY created_at LIMIT 1",
                (task_id,),
            ).fetchone()
        return self.get_decision(row["decision_id"]) if row else None

    def find_reusable_approval(self, approval_key: str, task_id: str) -> dict[str, Any] | None:
        init_database()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_usage_approval WHERE approval_key=? AND revoked_at IS NULL ORDER BY created_at DESC",
                (approval_key,),
            ).fetchall()
        for row in rows:
            approval = self._approval_dict(dict(row))
            if approval["approval_scope"] == "current_task":
                if approval["applicable_conditions"].get("task_id") != task_id:
                    continue
            return approval
        return None

    def approve(
        self,
        *,
        decision_id: str,
        approval_scope: str,
        reviewer_id: str,
        approved_payload: dict[str, Any],
        applicable_conditions: dict[str, Any],
        source_revision_hash: str,
        claim_revision_hash: str,
        equipment_revision: str,
        intended_use: str,
        approval_key: str,
        comment: str | None,
    ) -> dict[str, Any]:
        if approval_scope not in {"current_task", "process_prior"}:
            raise ValueError(f"invalid approval scope: {approval_scope}")
        decision = self.get_decision(decision_id)
        if decision["status"] == "rejected":
            raise ValueError("rejected decision cannot be approved")
        approval_id = _id("knowledge-approval")
        now = _now()
        candidate_id = decision["evidence_ids"][0] if decision["evidence_ids"] else decision_id
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO knowledge_usage_approval VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    approval_id,
                    decision_id,
                    approval_scope,
                    reviewer_id,
                    _json(approved_payload),
                    _json(applicable_conditions),
                    source_revision_hash,
                    claim_revision_hash,
                    equipment_revision,
                    intended_use,
                    approval_key,
                    comment,
                    now,
                    None,
                ),
            )
            uow.connection.execute(
                "UPDATE knowledge_usage_decision SET status=?, resolved_at=? WHERE decision_id=?",
                ("approved_task" if approval_scope == "current_task" else "approved_prior", now, decision_id),
            )
            self._append_action(
                uow.connection,
                decision_id,
                candidate_id,
                reviewer_id,
                "approve_task" if approval_scope == "current_task" else "approve_prior",
                approval_scope,
                comment,
                {"approval_id": approval_id, "approved_payload": approved_payload},
                now,
            )
            if approval_scope == "process_prior":
                self._create_process_priors(
                    uow.connection,
                    decision,
                    approved_payload,
                    applicable_conditions,
                    approval_id,
                    now,
                )
            uow.commit()
        return self.get_approval(approval_id)

    def reject(self, decision_id: str, reviewer_id: str, comment: str | None) -> dict[str, Any]:
        decision = self.get_decision(decision_id)
        now = _now()
        candidate_id = decision["evidence_ids"][0] if decision["evidence_ids"] else decision_id
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE knowledge_usage_decision SET status='rejected', resolved_at=? WHERE decision_id=?",
                (now, decision_id),
            )
            self._append_action(
                uow.connection,
                decision_id,
                candidate_id,
                reviewer_id,
                "reject_usage",
                None,
                comment,
                {},
                now,
            )
            uow.commit()
        return self.get_decision(decision_id)

    def revoke(self, approval_id: str, reviewer_id: str, comment: str | None) -> dict[str, Any]:
        approval = self.get_approval(approval_id)
        if approval["revoked_at"]:
            return approval
        decision = self.get_decision(approval["decision_id"])
        now = _now()
        candidate_id = decision["evidence_ids"][0] if decision["evidence_ids"] else decision["decision_id"]
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE knowledge_usage_approval SET revoked_at=? WHERE approval_id=?",
                (now, approval_id),
            )
            uow.connection.execute(
                "UPDATE process_prior SET status='revoked' WHERE condition_json LIKE ?",
                (f'%"_approval_id": "{approval_id}"%',),
            )
            self._append_action(
                uow.connection,
                decision["decision_id"],
                candidate_id,
                reviewer_id,
                "revoke_approval",
                approval["approval_scope"],
                comment,
                {"approval_id": approval_id},
                now,
            )
            uow.commit()
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_usage_approval WHERE approval_id=?", (approval_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"knowledge usage approval not found: {approval_id}")
        return self._approval_dict(dict(row))

    def _approval_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        row["approved_payload"] = _loads(row.pop("approved_payload_json"), {})
        row["applicable_conditions"] = _loads(row.pop("applicable_conditions_json"), {})
        return row

    def _append_action(
        self,
        connection,
        decision_id: str,
        candidate_id: str,
        reviewer_id: str,
        action: str,
        target_level: str | None,
        comment: str | None,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO knowledge_review_action VALUES (?,?,?,?,?,?,?,?,?)",
            (
                _id("knowledge-action"),
                decision_id,
                candidate_id,
                reviewer_id,
                action,
                target_level,
                comment,
                now,
                _json(payload),
            ),
        )

    def _create_process_priors(
        self,
        connection,
        decision: dict[str, Any],
        approved_payload: dict[str, Any],
        conditions: dict[str, Any],
        approval_id: str,
        now: str,
    ) -> None:
        for parameter in approved_payload.get("parameters") or []:
            if not all(key in parameter for key in ("parameter_name", "lower_bound", "upper_bound")):
                continue
            prior_conditions = {**conditions, "_approval_id": approval_id}
            connection.execute(
                "INSERT INTO process_prior VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _id("process-prior"),
                    parameter.get("candidate_id") or (decision["evidence_ids"][0] if decision["evidence_ids"] else None),
                    conditions.get("material"),
                    conditions.get("process_type"),
                    conditions.get("component_type"),
                    parameter["parameter_name"],
                    float(parameter["lower_bound"]),
                    float(parameter["upper_bound"]),
                    parameter.get("unit"),
                    _json(prior_conditions),
                    _json(decision["evidence_ids"]),
                    float(parameter.get("confidence", 0.5)),
                    "active",
                    now,
                ),
            )
