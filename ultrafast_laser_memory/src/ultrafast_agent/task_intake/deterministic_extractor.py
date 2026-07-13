from __future__ import annotations

import re
from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)


_CORRECTION_MARKERS = ("改为", "修改为", "更正为", "纠正为", "不是", "应为")
_BOOLEAN_TRUE = {"允许", "可以", "可", "是", "true", "yes"}
_BOOLEAN_FALSE = {"不允许", "不可以", "不可", "否", "false", "no"}
_SEGMENT_SPLIT = re.compile(r"[;；\n]+")
_NUMBER_WITH_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|mm|毫米|厘米|um|μm|µm)", re.I)


class ContextualDeterministicExtractor:
    def extract(
        self,
        message: str,
        current_spec: dict[str, Any],
        context: ClarificationContext,
    ) -> TaskSpecPatch:
        text = message.strip()
        ambiguities: list[dict[str, Any]] = []
        if self._ambiguous_short_answer(text, context):
            ambiguities.append(
                {
                    "evidence": text,
                    "candidate_fields": [
                        field for field in context.pending_fields if field in {"efficiency_requirement", "auxiliary"}
                    ],
                    "reason": "简答可对应多个待补字段，禁止按顺序猜测。",
                }
            )
            return TaskSpecPatch(
                unresolved_fields=list(context.pending_fields),
                ambiguities=ambiguities,
            )

        ordered = list(context.ordered_fields or context.pending_fields)
        segments = self._segments(text)
        if ordered and len(segments) == len(ordered):
            mapped: list[TaskFieldCandidate] = []
            compatible = True
            for field, segment in zip(ordered, segments):
                candidates = self._for_field(field, segment, contextual=True)
                if not candidates:
                    compatible = False
                    break
                mapped.extend(candidates)
            if compatible and all(current_spec.get(field) is None for field in ordered):
                return self._patch(mapped, context, ambiguities)

        if len(context.pending_fields) == 1:
            field = context.pending_fields[0]
            contextual = self._for_field(field, text, contextual=True)
            if contextual:
                return self._patch(contextual, context, ambiguities)

        candidates = self._explicit_candidates(text, context)
        return self._patch(candidates, context, ambiguities)

    @staticmethod
    def _segments(message: str) -> list[str]:
        values = []
        for segment in _SEGMENT_SPLIT.split(message):
            cleaned = re.sub(r"^\s*\d+\s*[、.)．]\s*", "", segment).strip(" \t。；;")
            if cleaned:
                values.append(cleaned)
        return values

    @staticmethod
    def _ambiguous_short_answer(message: str, context: ClarificationContext) -> bool:
        ambiguous = message.strip(" 。；;").lower() in {"无要求", "没有要求", "无", "没有"}
        targets = {"efficiency_requirement", "auxiliary"}.intersection(context.pending_fields)
        return ambiguous and len(targets) > 1

    def _patch(
        self,
        candidates: list[TaskFieldCandidate],
        context: ClarificationContext,
        ambiguities: list[dict[str, Any]],
    ) -> TaskSpecPatch:
        unique: dict[tuple[str, str], TaskFieldCandidate] = {}
        for candidate in candidates:
            unique[(candidate.field_name, repr(candidate.raw_value))] = candidate
        updates = list(unique.values())
        covered = {candidate.field_name for candidate in updates}
        return TaskSpecPatch(
            updates=updates,
            unresolved_fields=[field for field in context.pending_fields if field not in covered],
            ambiguities=ambiguities,
        )

    def _for_field(
        self,
        field: str,
        segment: str,
        *,
        contextual: bool,
    ) -> list[TaskFieldCandidate]:
        raw = segment.strip()
        lowered = raw.lower()
        source = "contextual_deterministic" if contextual else "deterministic_explicit"
        confidence = 0.99 if contextual else 0.96
        operation = "correct" if any(marker in raw for marker in _CORRECTION_MARKERS) else "fill"

        if field == "layer_cut_allowed":
            value = self._boolean_value(lowered)
            if value is None and any(marker in lowered for marker in ("允许层切", "可多次分层", "分层加工")):
                value = True
            if value is None and any(marker in lowered for marker in ("禁止层切", "不可分层", "不分层加工")):
                value = False
            return [self._candidate(field, value, raw, source, confidence, operation)] if value is not None else []
        if field in {"cut_length_mm", "thickness_mm"}:
            match = _NUMBER_WITH_UNIT.search(lowered)
            if not match:
                return []
            candidates = [self._candidate(field, match.group(1), match.group(0), source, confidence, operation, match.group(2))]
            if field == "cut_length_mm":
                contour = self._contour_value(lowered)
                if contour:
                    evidence = next(marker for marker in ("直线", "曲线", "圆弧", "圆形") if marker in lowered)
                    candidates.append(self._candidate("contour_type", contour, evidence, source, confidence, operation))
            return candidates
        if field == "quality_requirement":
            if "无分层" in lowered or "不得分层" in lowered or "delamination" in lowered:
                return [self._candidate(field, "no_delamination", raw, source, confidence, operation)]
            if any(marker in lowered for marker in ("无热损伤", "无明显热损伤")):
                return [self._candidate(field, "no_thermal_damage", raw, source, confidence, operation)]
            return []
        if field == "efficiency_requirement":
            if any(marker in lowered for marker in ("无效率要求", "无硬性限制", "不限时间", "效率无要求")):
                return [self._candidate(field, "none", raw, source, confidence, operation)]
            return []
        if field == "auxiliary":
            if "压缩空气" in lowered:
                return [self._candidate(field, "compressed_air", "压缩空气", source, confidence, operation)]
            if "氮气" in lowered:
                return [self._candidate(field, "nitrogen", "氮气", source, confidence, operation)]
            if any(marker in lowered for marker in ("无辅助气体", "不用辅助气体")):
                return [self._candidate(field, "none", raw, source, confidence, operation)]
            return []
        if field == "material":
            if any(marker in lowered for marker in ("碳纤维", "cfrp", "t300")):
                value = "CFRP_T300" if "t300" in lowered else "CFRP"
                return [self._candidate(field, value, raw, source, confidence, operation)]
            if "金刚石" in lowered or "diamond" in lowered:
                return [self._candidate(field, "diamond", raw, source, confidence, operation)]
            return []
        if field == "process_type":
            if "切割" in lowered or "cutting" in lowered:
                return [self._candidate(field, "cutting", raw, source, confidence, operation)]
            return []
        return []

    def _explicit_candidates(
        self,
        message: str,
        context: ClarificationContext,
    ) -> list[TaskFieldCandidate]:
        text = message.lower()
        candidates: list[TaskFieldCandidate] = []
        for field in ("material", "process_type", "quality_requirement", "efficiency_requirement", "auxiliary"):
            candidates.extend(self._for_field(field, message, contextual=False))

        thickness = re.search(
            r"(?:板厚|材料厚度|厚度)\s*(?:改为|修改为|更正为|应为|是|为|=|:|：)?\s*"
            r"(\d+(?:\.\d+)?)\s*(cm|mm|毫米|厘米|um|μm|µm)|"
            r"(\d+(?:\.\d+)?)\s*(cm|mm|毫米|厘米|um|μm|µm)\s*厚",
            text,
            re.I,
        )
        if thickness:
            candidates.extend(self._for_field("thickness_mm", thickness.group(0), contextual=False))

        cut = re.search(
            r"(?:切割(?:总)?长度|总切长|切长)\s*(?:为|=|:|：)?\s*"
            r"\d+(?:\.\d+)?\s*(?:cm|mm|毫米|厘米|um|μm|µm)(?:\s*(?:直线|曲线|圆弧|圆形))?|"
            r"\d+(?:\.\d+)?\s*(?:cm|mm|毫米|厘米|um|μm|µm)\s*(?:直线|曲线|圆弧|圆形)",
            text,
            re.I,
        )
        if cut:
            candidates.extend(self._for_field("cut_length_mm", cut.group(0), contextual=False))

        if any(marker in text for marker in ("允许层切", "可多次分层", "分层加工", "禁止层切", "不可分层")):
            candidates.extend(self._for_field("layer_cut_allowed", message, contextual=False))
        if "自动焦点跟踪" in text or "自动z轴" in text:
            candidates.append(
                self._candidate("focus_tracking", True, message, "deterministic_explicit", 0.96, "fill")
            )
        return candidates

    @staticmethod
    def _boolean_value(value: str) -> bool | None:
        cleaned = value.strip(" 。；;").lower()
        if cleaned in _BOOLEAN_TRUE:
            return True
        if cleaned in _BOOLEAN_FALSE:
            return False
        return None

    @staticmethod
    def _contour_value(value: str) -> str | None:
        if "直线" in value:
            return "straight"
        if "曲线" in value:
            return "curve"
        if "圆弧" in value:
            return "arc"
        if "圆形" in value:
            return "circle"
        return None

    @staticmethod
    def _candidate(
        field: str,
        value: Any,
        evidence: str,
        source: str,
        confidence: float,
        operation: str,
        unit: str | None = None,
    ) -> TaskFieldCandidate:
        return TaskFieldCandidate(
            field_name=field,
            raw_value=value,
            unit=unit,
            evidence=evidence,
            extraction_source=source,
            confidence=confidence,
            operation=operation,
        )


def legacy_task_snapshot(message: str) -> dict[str, Any]:
    """Compatibility adapter for non-process status views; semantic rules live outside workflow status."""
    context = ClarificationContext(
        workflow_type="task_intake",
        stage="INTAKE",
        pending_fields=[],
        ordered_fields=[],
    )
    patch = ContextualDeterministicExtractor().extract(message, {}, context)
    from ultrafast_agent.task_intake.normalizer import TaskFieldNormalizer

    normalized = TaskFieldNormalizer.normalize(patch)
    task = {candidate.field_name: candidate.normalized_value for candidate in normalized.updates}
    text = message.lower()
    if "crl" in text or "透镜" in text or "x-ray" in text:
        task["component_type"] = "CRL"
    elif task.get("process_type") == "cutting":
        task["component_type"] = "workpiece"
    if "飞秒" in text or "femtosecond" in text or "超快" in text:
        task["process_type"] = "femtosecond_laser_micromachining"
    roughness = re.search(r"ra\s*[<小于]*\s*(\d+(?:\.\d+)?)\s*(nm|um|µm)?", message, re.I)
    if roughness:
        task["roughness_target"] = f"Ra < {roughness.group(1)} {roughness.group(2) or 'nm'}"
    if "单晶" in message or "single crystal" in text:
        task["diamond_type"] = "single_crystal"
    if any(marker in text for marker in ("1030", "515", "800", "fs", "khz", "w")):
        task["laser_system"] = "mentioned"
    if "后处理" in message:
        task["post_processing_allowed"] = "mentioned"
    return task
