from __future__ import annotations

import re
import unicodedata

from ultrafast_agent.task_intake.schemas import ClarificationContext, TaskFieldCandidate, TaskSpecPatch


STRICT_EXTRACTOR_VERSION = "strict-kv-v1"

_ALIASES = {
    "材料": "material",
    "材料牌号": "material",
    "material": "material",
    "加工类型": "process_type",
    "工艺": "process_type",
    "process_type": "process_type",
    "厚度": "thickness_mm",
    "板厚": "thickness_mm",
    "thickness": "thickness_mm",
    "thickness_mm": "thickness_mm",
    "质量要求": "quality_requirement",
    "quality_requirement": "quality_requirement",
    "切割长度": "cut_length_mm",
    "总切割长度": "cut_length_mm",
    "cut_length": "cut_length_mm",
    "cut_length_mm": "cut_length_mm",
    "轮廓": "contour_type",
    "轮廓类型": "contour_type",
    "contour": "contour_type",
    "contour_type": "contour_type",
    "效率要求": "efficiency_requirement",
    "efficiency_requirement": "efficiency_requirement",
    "辅助介质": "auxiliary",
    "辅助气体": "auxiliary",
    "auxiliary": "auxiliary",
    "允许分层切割": "layer_cut_allowed",
    "允许多次分层切割": "layer_cut_allowed",
    "layer_cut_allowed": "layer_cut_allowed",
}


class StrictKeyValueParser:
    """Parse only explicit alias=value input; never infer a field from a value."""

    def parse(self, message: str, context: ClarificationContext) -> TaskSpecPatch | None:
        normalized = unicodedata.normalize("NFKC", message)
        segments = [item.strip() for item in re.split(r"[;；\n]+", normalized) if item.strip()]
        if not segments or any("=" not in item for item in segments):
            return None
        updates: list[TaskFieldCandidate] = []
        for segment in segments:
            key, value = (part.strip() for part in segment.split("=", 1))
            field = _ALIASES.get(key.lower())
            if field is None or not value:
                return None
            evidence = self._evidence_from_original(message, value)
            updates.append(TaskFieldCandidate(
                field_name=field,
                raw_value=value,
                unit=None,
                evidence=evidence,
                extraction_source="strict_key_value",
                confidence=1.0,
                operation="fill",
            ))
        covered = {item.field_name for item in updates}
        return TaskSpecPatch(
            updates=updates,
            unresolved_fields=[field for field in context.pending_fields if field not in covered],
            extraction_version=STRICT_EXTRACTOR_VERSION,
            extraction_mode="strict_key_value",
            schema_valid=True,
        )

    @staticmethod
    def _evidence_from_original(message: str, normalized_value: str) -> str:
        if normalized_value in message:
            return normalized_value
        target = unicodedata.normalize("NFKC", normalized_value)
        for token in re.split(r"[;；\n=＝]+", message):
            stripped = token.strip()
            if unicodedata.normalize("NFKC", stripped) == target:
                return stripped
        return normalized_value
