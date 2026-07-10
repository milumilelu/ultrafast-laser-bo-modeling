from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable

from ultrafast_domain.review.classification import ClaimClassificationService


BACKGROUND_USES = {
    "background_explanation",
    "literature_search",
    "defect_summary",
    "measurement_method",
    "raw_value_display",
}
REVIEWED_USES = {
    "parameter_recommendation",
    "bo_search_bound",
    "candidate_filter",
    "process_prior_promotion",
    "safety_threshold",
    "conflicting_knowledge",
}


class GateStatus(StrEnum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class GateDecision:
    status: GateStatus
    intended_use: str
    risk_level: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    classifications: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["reasons"] = list(self.reasons)
        value["evidence_ids"] = list(self.evidence_ids)
        value["classifications"] = list(self.classifications)
        return value


class KnowledgeUseGate:
    @staticmethod
    def evaluate(
        task_spec: dict[str, Any],
        intended_use: str,
        evidence: Iterable[dict[str, Any]],
        equipment: dict[str, Any],
    ) -> GateDecision:
        items = list(evidence)
        classifications = tuple(
            ClaimClassificationService().classify(str(item.get("claim") or "")).to_dict()
            for item in items
        )
        evidence_ids = tuple(str(item.get("evidence_id") or item.get("candidate_id") or f"evidence-{index}") for index, item in enumerate(items))
        if intended_use in BACKGROUND_USES:
            return GateDecision(
                GateStatus.ALLOWED,
                intended_use,
                max((item["risk_level"] for item in classifications), default="low", key=_risk_rank),
                ("background_use_does_not_require_approval",),
                evidence_ids,
                classifications,
            )
        if intended_use not in REVIEWED_USES:
            return GateDecision(
                GateStatus.BLOCKED,
                intended_use,
                "high",
                ("unknown_intended_use",),
                evidence_ids,
                classifications,
            )
        if not equipment.get("active") or not equipment.get("revision_id"):
            return GateDecision(
                GateStatus.BLOCKED,
                intended_use,
                "high",
                ("active_equipment_revision_required",),
                evidence_ids,
                classifications,
            )
        if not items:
            return GateDecision(
                GateStatus.BLOCKED,
                intended_use,
                "high",
                ("no_evidence_for_high_risk_use",),
                evidence_ids,
                classifications,
            )
        if any(str(item.get("status") or item.get("review_status")).lower() in {"rejected", "withdrawn"} for item in items):
            return GateDecision(
                GateStatus.BLOCKED,
                intended_use,
                "high",
                ("rejected_evidence",),
                evidence_ids,
                classifications,
            )
        bounds_violation = _equipment_violation(items, equipment.get("machine_bounds") or {})
        if bounds_violation:
            return GateDecision(
                GateStatus.BLOCKED,
                intended_use,
                "critical",
                (bounds_violation,),
                evidence_ids,
                classifications,
            )
        approved = all(item.get("approval_id") and not item.get("approval_revoked") for item in items)
        risk = max((item["risk_level"] for item in classifications), default="medium", key=_risk_rank)
        if approved:
            return GateDecision(
                GateStatus.ALLOWED,
                intended_use,
                risk,
                ("matching_active_approval",),
                evidence_ids,
                classifications,
            )
        reasons = ["human_approval_required"]
        if any(item.get("conflict_flag") for item in items):
            reasons.append("conflicting_evidence")
        return GateDecision(
            GateStatus.APPROVAL_REQUIRED,
            intended_use,
            risk,
            tuple(reasons),
            evidence_ids,
            classifications,
        )


def build_approval_key(
    *,
    source_revision: str,
    claim_revision: str,
    material: str | None,
    material_grade: str | None,
    process_type: str | None,
    equipment_revision: str,
    intended_use: str,
    conditions: dict[str, Any],
) -> str:
    payload = {
        "source_revision": source_revision,
        "claim_revision": claim_revision,
        "material": material,
        "material_grade": material_grade,
        "process_type": process_type,
        "equipment_revision": equipment_revision,
        "intended_use": intended_use,
        "condition_hash": hashlib.sha256(
            json.dumps(conditions, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _risk_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(value, 2)


def _equipment_violation(items: list[dict[str, Any]], bounds: dict[str, Any]) -> str | None:
    for item in items:
        parameters = item.get("parameters") or item.get("parameter") or {}
        for name, value in parameters.items():
            if name not in bounds:
                continue
            lower, upper = bounds[name]
            if isinstance(value, (list, tuple)) and len(value) == 2:
                proposed_lower, proposed_upper = map(float, value)
                if proposed_lower < float(lower) or proposed_upper > float(upper):
                    return f"proposed_{name}_outside_equipment_bounds"
            elif isinstance(value, (int, float)) and not (float(lower) <= float(value) <= float(upper)):
                return f"proposed_{name}_outside_equipment_bounds"
    return None
