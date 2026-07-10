from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable


VALID_CLAIM_TYPES = {"background", "mechanism", "measurement", "trend", "numeric_range", "recommendation", "safety"}
VALID_RISKS = {"low", "medium", "high", "critical"}
NUMERIC_UNIT = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:fs|ps|ns|nm|µm|um|mm|w|kw|khz|mhz|j|mj|uj|%|mm/s))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ClaimClassification:
    claim_type: str
    risk_level: str
    allowed_uses: tuple[str, ...]
    requires_review_before: tuple[str, ...]
    reason_summary: str
    classification_source: str = "deterministic_fallback"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_uses"] = list(self.allowed_uses)
        value["requires_review_before"] = list(self.requires_review_before)
        return value


class ClaimClassificationService:
    def __init__(self, llm_classifier: Callable[[str], dict[str, Any]] | None = None):
        self.llm_classifier = llm_classifier

    def classify(self, claim: str) -> ClaimClassification:
        if self.llm_classifier is not None:
            try:
                return self._validate_llm(self.llm_classifier(claim))
            except Exception:
                pass
        return self._deterministic(claim)

    def _validate_llm(self, value: dict[str, Any]) -> ClaimClassification:
        claim_type = str(value["claim_type"])
        risk = str(value["risk_level"])
        if claim_type not in VALID_CLAIM_TYPES or risk not in VALID_RISKS:
            raise ValueError("invalid LLM classification enum")
        return ClaimClassification(
            claim_type=claim_type,
            risk_level=risk,
            allowed_uses=tuple(map(str, value.get("allowed_uses", []))),
            requires_review_before=tuple(map(str, value.get("requires_review_before", []))),
            reason_summary=str(value.get("reason_summary") or "LLM classification"),
            classification_source="llm",
        )

    def _deterministic(self, claim: str) -> ClaimClassification:
        text = claim.lower()
        numeric = bool(NUMERIC_UNIT.search(claim))
        safety = any(token in text for token in ("safety", "damage threshold", "损伤阈值", "安全阈值", "爆裂", "失效阈值"))
        recommendation = any(token in text for token in ("recommend", "optimal", "should use", "推荐", "最优", "应采用"))
        bounded = any(token in text for token in ("upper limit", "lower limit", "range", "上限", "下限", "范围"))
        measurement = any(token in text for token in ("measured by", "measurement", "sem", "profilometer", "测量", "表征"))
        mechanism = any(token in text for token in ("mechanism", "caused by", "due to", "机制", "导致", "由于"))
        if safety:
            return ClaimClassification(
                "safety",
                "critical",
                ("background_explanation",),
                ("safety_threshold", "parameter_recommendation", "bo_search_bound"),
                "包含安全或损伤阈值。",
            )
        if recommendation:
            return ClaimClassification(
                "recommendation",
                "high",
                ("background_explanation",),
                ("parameter_recommendation", "bo_search_bound", "candidate_filter"),
                "包含推荐或最优性表述。",
            )
        if numeric and bounded:
            return ClaimClassification(
                "numeric_range",
                "high",
                ("background_explanation", "raw_value_display"),
                ("parameter_recommendation", "bo_search_bound", "candidate_filter"),
                "包含带单位的上下限或范围。",
            )
        if numeric:
            return ClaimClassification(
                "numeric_range",
                "medium",
                ("background_explanation", "raw_value_display"),
                ("parameter_recommendation", "bo_search_bound"),
                "包含具体数值和单位。",
            )
        if measurement:
            return ClaimClassification(
                "measurement",
                "low",
                ("background_explanation", "measurement_method"),
                (),
                "仅描述测量或表征方法。",
            )
        if mechanism:
            return ClaimClassification(
                "mechanism",
                "low",
                ("background_explanation",),
                (),
                "描述机制，不直接给出参数。",
            )
        return ClaimClassification(
            "background",
            "low",
            ("background_explanation",),
            (),
            "未检测到数值、推荐或安全阈值。",
        )
