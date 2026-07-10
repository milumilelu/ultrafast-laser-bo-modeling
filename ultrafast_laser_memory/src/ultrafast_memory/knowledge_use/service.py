from __future__ import annotations

import hashlib
import json
from typing import Any

from ultrafast_domain.review import KnowledgeUseGate, build_approval_key
from ultrafast_integrations.storage.knowledge_use_repository import KnowledgeUseRepository


class KnowledgeUseApplicationService:
    def __init__(self, repository: KnowledgeUseRepository | None = None):
        self.repository = repository or KnowledgeUseRepository()

    def evaluate(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_spec = {"task_id": task_id, **(payload.get("task_spec") or {})}
        intended_use = payload["intended_use"]
        evidence = list(payload.get("evidence") or [])[:5]
        equipment = payload.get("equipment") or {}
        approval_material = self._approval_material(task_spec, intended_use, evidence, equipment)
        # Approval markers are repository-owned. Never trust client-supplied IDs.
        gate_evidence = [
            {key: value for key, value in item.items() if key not in {"approval_id", "approval_revoked"}}
            for item in evidence
        ]
        decision = KnowledgeUseGate.evaluate(task_spec, intended_use, gate_evidence, equipment)
        result = decision.to_dict()
        result["task_id"] = task_id
        result["reused_approval"] = None
        # Background use and intrinsic safety blocks do not require review storage.
        if result["status"] != "approval_required":
            return result
        try:
            reusable = self.repository.find_reusable_approval(
                approval_material["approval_key"], task_id
            )
        except Exception:
            return self._review_unavailable(task_id, result)
        if reusable:
            for item in gate_evidence:
                item["approval_id"] = reusable["approval_id"]
            result = KnowledgeUseGate.evaluate(
                task_spec, intended_use, gate_evidence, equipment
            ).to_dict()
            result["task_id"] = task_id
            result["reused_approval"] = reusable
        if result["status"] != "approval_required":
            return result
        try:
            existing = self.repository.find_task_decision(task_id)
        except Exception:
            return self._review_unavailable(task_id, result)
        if existing:
            return {
                **result,
                "decision_id": existing["decision_id"],
                "decision_status": existing["status"],
                "reused_decision": True,
            }
        proposed_usage = {
            **(payload.get("proposed_usage") or {}),
            "task_spec": task_spec,
            "equipment_revision": equipment.get("revision_id"),
            "approval_material": approval_material,
            "classifications": result["classifications"],
        }
        try:
            record = self.repository.create_decision(
                session_id=payload.get("session_id"),
                task_id=task_id,
                intended_use=intended_use,
                evidence_ids=result["evidence_ids"],
                proposed_usage=proposed_usage,
                risk_level=result["risk_level"],
            )
        except Exception:
            return self._review_unavailable(task_id, result)
        return {
            **result,
            "decision_id": record["decision_id"],
            "decision_status": record["status"],
            "reused_decision": False,
            "truncated_evidence_count": max(0, len(payload.get("evidence") or []) - 5),
        }

    @staticmethod
    def _review_unavailable(task_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            **decision,
            "status": "blocked",
            "risk_level": "critical",
            "reasons": ["review_service_unavailable"],
            "task_id": task_id,
            "reused_approval": None,
            "fail_closed": True,
        }

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        return self.repository.get_decision(decision_id)

    def approve_task(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._approve(decision_id, payload, "current_task")

    def approve_prior(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._approve(decision_id, payload, "process_prior")

    def reject(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.reject(decision_id, payload["reviewer_id"], payload.get("comment"))

    def revoke(self, approval_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.revoke(approval_id, payload["reviewer_id"], payload.get("comment"))

    def _approve(self, decision_id: str, payload: dict[str, Any], scope: str) -> dict[str, Any]:
        decision = self.repository.get_decision(decision_id)
        material = decision["proposed_usage"].get("approval_material") or {}
        conditions = dict(material.get("conditions") or {})
        conditions["task_id"] = decision["task_id"]
        approved_payload = payload.get("approved_payload") or {
            "parameters": decision["proposed_usage"].get("parameters") or []
        }
        return self.repository.approve(
            decision_id=decision_id,
            approval_scope=scope,
            reviewer_id=payload["reviewer_id"],
            approved_payload=approved_payload,
            applicable_conditions=conditions,
            source_revision_hash=material["source_revision_hash"],
            claim_revision_hash=material["claim_revision_hash"],
            equipment_revision=material["equipment_revision"],
            intended_use=decision["intended_use"],
            approval_key=material["approval_key"],
            comment=payload.get("comment"),
        )

    def _approval_material(
        self,
        task_spec: dict[str, Any],
        intended_use: str,
        evidence: list[dict[str, Any]],
        equipment: dict[str, Any],
    ) -> dict[str, Any]:
        source_revision_hash = _combined_hash(
            [str(item.get("source_revision") or item.get("source_id") or item.get("evidence_id") or "unknown") for item in evidence]
        )
        claim_revision_hash = _combined_hash(
            [str(item.get("claim_revision") or _hash(str(item.get("claim") or ""))) for item in evidence]
        )
        conditions = {
            "material": task_spec.get("material"),
            "material_grade": task_spec.get("material_grade"),
            "process_type": task_spec.get("process_type"),
            "component_type": task_spec.get("component_type"),
            **(task_spec.get("conditions") or {}),
        }
        equipment_revision = str(equipment.get("revision_id") or "missing")
        return {
            "source_revision_hash": source_revision_hash,
            "claim_revision_hash": claim_revision_hash,
            "equipment_revision": equipment_revision,
            "conditions": conditions,
            "approval_key": build_approval_key(
                source_revision=source_revision_hash,
                claim_revision=claim_revision_hash,
                material=task_spec.get("material"),
                material_grade=task_spec.get("material_grade"),
                process_type=task_spec.get("process_type"),
                equipment_revision=equipment_revision,
                intended_use=intended_use,
                conditions=conditions,
            ),
        }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _combined_hash(values: list[str]) -> str:
    return _hash(json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":")))
