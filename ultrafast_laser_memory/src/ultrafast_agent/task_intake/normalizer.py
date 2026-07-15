from __future__ import annotations

import re
from typing import Any

from ultrafast_agent.task_intake.schemas import TaskFieldCandidate, TaskSpecPatch


_LENGTH_FACTORS = {
    "mm": 1.0,
    "毫米": 1.0,
    "cm": 10.0,
    "厘米": 10.0,
    "um": 0.001,
    "μm": 0.001,
    "µm": 0.001,
}


class TaskFieldNormalizer:
    @classmethod
    def normalize(cls, patch: TaskSpecPatch) -> TaskSpecPatch:
        updates = []
        rejected = list(patch.rejected_candidates)
        for candidate in patch.updates:
            try:
                updates.append(cls._normalize_candidate(candidate))
            except (TypeError, ValueError) as exc:
                rejected.append(
                    {
                        "field_name": candidate.field_name,
                        "evidence": candidate.evidence,
                        "reason": f"normalization_failed:{type(exc).__name__}",
                    }
                )
        return patch.model_copy(update={"updates": updates, "rejected_candidates": rejected})

    @classmethod
    def _normalize_candidate(cls, candidate: TaskFieldCandidate) -> TaskFieldCandidate:
        field = candidate.field_name
        raw = candidate.raw_value
        value: Any = raw
        unit = candidate.unit
        if field in {"thickness_mm", "cut_length_mm", "hole_diameter_mm", "hole_depth_mm"}:
            number, parsed_unit = cls._length(raw, unit)
            value = number * _LENGTH_FACTORS[parsed_unit]
            unit = "mm"
        elif field in {"layer_cut_allowed", "through_hole"}:
            value = cls._boolean(raw)
        elif field == "auxiliary":
            value = cls._enum(raw, {"压缩空气": "compressed_air", "氮气": "nitrogen", "无": "none"})
        elif field == "contour_type":
            value = cls._enum(raw, {"直线": "straight", "曲线": "curve", "圆弧": "arc", "圆形": "circle"})
        elif field == "efficiency_requirement":
            text = str(raw).strip().lower()
            value = "none" if text in {"无", "无要求", "无效率要求", "时间无所谓", "none"} else raw
        elif field == "process_type":
            value = cls._enum(raw, {
                "通孔": "hole_drilling",
                "钻孔": "drilling",
                "打孔": "drilling",
                "切割": "cutting",
                "刻蚀": "engraving",
                "开槽": "groove_machining",
                "槽加工": "groove_machining",
                "矩形槽": "groove_machining",
            })
        elif field == "geometry":
            value = cls._geometry(raw)
        elif field == "material":
            value = cls._enum(raw, {
                "碳纤维复合板": "CFRP",
                "碳纤维复合材料": "CFRP",
                "碳纤维": "CFRP",
                "金刚石": "diamond",
            })
        elif field == "quality_requirement":
            value = cls._enum(raw, {
                "切缝区域无分层": "no_delamination",
                "切缝不要分层": "no_delamination",
                "无分层": "no_delamination",
                "无明显热损伤": "no_thermal_damage",
            })
        return candidate.model_copy(update={"normalized_value": value, "unit": unit})

    @classmethod
    def _geometry(cls, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise TypeError("geometry must be an object")
        geometry = dict(raw)
        feature_type = geometry.get("feature_type")
        description = geometry.get("description")
        if not isinstance(feature_type, str) or not feature_type.strip():
            if isinstance(description, str) and description.strip():
                geometry["feature_type"] = "custom"
            else:
                raise ValueError("geometry requires feature_type or description")
        dimensions = geometry.get("dimensions")
        if dimensions is not None:
            if not isinstance(dimensions, dict):
                raise TypeError("geometry dimensions must be an object")
            normalized_dimensions: dict[str, float] = {}
            for name, raw_value in dimensions.items():
                if not str(name).endswith("_mm"):
                    raise ValueError("geometry dimension keys must end with _mm")
                number, unit = cls._length(raw_value, None)
                normalized_dimensions[str(name)] = number * _LENGTH_FACTORS[unit]
            geometry["dimensions"] = normalized_dimensions
        if geometry.get("depth_mm") is not None:
            number, unit = cls._length(geometry["depth_mm"], None)
            geometry["depth_mm"] = number * _LENGTH_FACTORS[unit]
        return geometry

    @staticmethod
    def _length(raw: Any, unit: str | None) -> tuple[float, str]:
        if isinstance(raw, bool):
            raise TypeError("boolean is not a length")
        if isinstance(raw, (int, float)):
            parsed_unit = unit or "mm"
            if parsed_unit not in _LENGTH_FACTORS:
                raise ValueError("unsupported length unit")
            return float(raw), parsed_unit
        match = re.search(r"(\d+(?:\.\d+)?)\s*(cm|mm|毫米|厘米|um|μm|µm)?", str(raw), re.I)
        if not match:
            raise ValueError("length value not found")
        parsed_unit = unit or match.group(2) or "mm"
        parsed_unit = parsed_unit.lower() if parsed_unit.lower() in {"cm", "mm", "um"} else parsed_unit
        if parsed_unit not in _LENGTH_FACTORS:
            raise ValueError("unsupported length unit")
        return float(match.group(1)), parsed_unit

    @staticmethod
    def _boolean(raw: Any) -> bool:
        if isinstance(raw, bool):
            return raw
        value = str(raw).strip(" 。；;").lower()
        if value in {"允许", "可以", "可", "是", "true", "yes", "1"}:
            return True
        if value in {"不允许", "不可以", "不可", "否", "false", "no", "0"}:
            return False
        raise ValueError("boolean value not recognized")

    @staticmethod
    def _enum(raw: Any, mapping: dict[str, str]) -> Any:
        value = str(raw).strip()
        if value in mapping.values():
            return value
        for marker, normalized in mapping.items():
            if marker in value:
                return normalized
        return raw
