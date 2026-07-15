from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_LENGTH = r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|um|μm|µm)"
_CORRECTION = re.compile(r"改为|改成|更正|修正|调整为|应为|换成|不是.+(?:而是|是)")


@dataclass(slots=True)
class TaskIntakeResult:
    """A non-controlling patch produced before the Main Agent plans."""

    context_updates: dict[str, Any] = field(default_factory=dict)
    skill_hints: list[str] = field(default_factory=lambda: ["task_understanding"])
    changed_fields: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    blocking_fields: list[str] = field(default_factory=list)
    summary: str = "未发现可安全确定的结构化任务事实。"


@dataclass(slots=True)
class TaskSpecPatch:
    candidates: list[tuple[str, Any, str]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    extraction_version: str = "hybrid-deterministic-v2"


@dataclass(slots=True)
class TaskSpecMergeResult:
    task_updates: dict[str, Any]
    applied_fields: list[str]
    conflicts: list[dict[str, Any]]
    field_provenance: dict[str, dict[str, Any]]


class TaskSpecMergeService:
    """Protect established facts and apply only explicit corrections."""

    @staticmethod
    def merge(
        task: dict[str, Any], patch: TaskSpecPatch, *, correcting: bool,
    ) -> TaskSpecMergeResult:
        updates: dict[str, Any] = {}
        applied: list[str] = []
        conflicts: list[dict[str, Any]] = []
        provenance: dict[str, dict[str, Any]] = {}
        for path, value, evidence in patch.candidates:
            current = _read_path(task, path)
            if current is not None and current != value and not correcting:
                conflicts.append({
                    "field": path,
                    "existing_value": current,
                    "candidate_value": value,
                    "evidence": evidence,
                    "reason": "explicit_correction_required",
                })
                continue
            if current == value:
                continue
            _write_path(updates, path, value)
            applied.append(path)
            provenance[path] = {
                "evidence": evidence,
                "source": "user_message",
                "extractor_version": patch.extraction_version,
            }
        return TaskSpecMergeResult(updates, applied, conflicts, provenance)


class HybridTaskFieldExtractionService:
    """Merge explicit and contextual task facts without making workflow decisions.

    This service deliberately extracts only user-stated task facts. Process
    parameters remain the responsibility of governed recommendation tools.
    """

    def prepare(self, message: str, working_context: dict[str, Any]) -> TaskIntakeResult:
        task = dict(working_context.get("task") or {})
        patch = self.extract(message, task)
        merged = TaskSpecMergeService.merge(
            task, patch, correcting=bool(_CORRECTION.search(message)),
        )
        projected = _deep_merge_copy(task, merged.task_updates)
        blocking = _blocking_fields(projected)
        intake_state = {
            "extractor": patch.extraction_version,
            "changed_fields": merged.applied_fields,
            "field_provenance": merged.field_provenance,
            "conflicts": merged.conflicts,
            "ambiguities": patch.ambiguities,
            "blocking_fields": blocking,
        }
        context_updates: dict[str, Any] = {"task_intake": intake_state}
        if merged.task_updates:
            context_updates["task"] = merged.task_updates
        skills = ["task_understanding"]
        if projected.get("material") and projected.get("process_intent"):
            skills.extend(["evidence_research", "process_planning"])
        return TaskIntakeResult(
            context_updates=context_updates,
            skill_hints=skills,
            changed_fields=merged.applied_fields,
            conflicts=merged.conflicts,
            ambiguities=patch.ambiguities,
            blocking_fields=blocking,
            summary=(
                f"已合并 {len(merged.applied_fields)} 项用户明确事实。"
                if merged.applied_fields else "本轮没有新的高置信任务事实。"
            ),
        )

    def extract(self, message: str, task: dict[str, Any]) -> TaskSpecPatch:
        return TaskSpecPatch(
            candidates=self._extract(message, task),
            ambiguities=self._ambiguities(message, task),
        )

    def _extract(self, message: str, task: dict[str, Any]) -> list[tuple[str, Any, str]]:
        text = message.strip()
        lowered = text.lower()
        values: list[tuple[str, Any, str]] = []

        process = None
        if re.search(r"切割|切断|cutting", lowered):
            process = "cutting"
        elif re.search(r"矩形槽|开槽|槽加工", lowered):
            process = "groove_machining"
        elif re.search(r"通孔|钻孔|打孔", lowered):
            process = "through_hole_drilling"
        if process:
            values.append(("process_intent", process, text))

        material_found = False
        if re.search(r"碳纤维|cfrp", lowered):
            material_evidence = _evidence(text, r"碳纤维(?:复合板|复合材料|板)?|CFRP")
            values.extend([
                ("material.name", "CFRP", material_evidence),
                ("material.description", material_evidence, material_evidence),
            ])
            material_found = True
        elif re.search(r"金刚石|钻石|diamond", lowered):
            material_evidence = _evidence(text, r"金刚石|钻石|diamond")
            values.extend([
                ("material.name", "diamond", material_evidence),
                ("material.description", material_evidence, material_evidence),
            ])
            material_found = True
        else:
            explicit = re.search(r"材料\s*[=＝:：]\s*([^，。；;]+)", text)
            if explicit:
                values.append(("material.name", explicit.group(1).strip(), explicit.group(0)))
                material_found = True
        if not material_found:
            situated = re.search(r"(?:在)?([^，。；;]+?)(?:上|中)加工", text)
            if situated:
                raw_material = re.sub(r"^在", "", situated.group(1)).strip()
                raw_material = re.sub(
                    r"^\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米|um|μm|µm)\s*厚的?",
                    "", raw_material, flags=re.I,
                ).strip()
                if raw_material:
                    values.extend([
                        ("material.name", raw_material, situated.group(0)),
                        ("material.description", raw_material, situated.group(0)),
                    ])
        grade = re.search(r"(?:板号|型号|牌号)?\s*(T\d{3,4})", text, re.I)
        if grade:
            values.append(("material.grade", grade.group(1).upper(), grade.group(0)))

        thickness = re.search(
            rf"(?:板厚|材料厚度|厚度)\s*(?:改为|改成|更正为|修正为|是|为|=|:|：)?\s*{_LENGTH}",
            text, re.I,
        ) or re.search(rf"{_LENGTH}\s*厚", text, re.I)
        if thickness:
            values.append((
                "workpiece.thickness_mm",
                _millimetres(thickness.group("value"), thickness.group("unit")),
                thickness.group(0),
            ))

        groove = re.search(
            r"(?P<length>\d+(?:\.\d+)?)\s*[*xX×]\s*(?P<width>\d+(?:\.\d+)?)\s*"
            r"(?P<unit>mm|毫米|cm|厘米|um|μm|µm)?\s*的?矩形槽",
            text, re.I,
        )
        if groove:
            unit = groove.group("unit") or "mm"
            values.extend([
                ("geometry.feature_type", "rectangular_groove", groove.group(0)),
                ("geometry.dimensions.length_mm", _millimetres(groove.group("length"), unit), groove.group(0)),
                ("geometry.dimensions.width_mm", _millimetres(groove.group("width"), unit), groove.group(0)),
                ("geometry.description", (
                    f"{groove.group('length')}×{groove.group('width')} {unit} 矩形槽"
                ), groove.group(0)),
            ])
        if re.search(r"贯穿|通槽", text):
            values.append(("geometry.through", True, _evidence(text, r"贯穿|通槽")))
        depth = re.search(
            rf"(?:槽深|深度)\s*(?:改为|改成|更正为|修正为|是|为|=|:|：)?\s*{_LENGTH}",
            text, re.I,
        )
        if depth:
            values.append((
                "geometry.depth_mm",
                _millimetres(depth.group("value"), depth.group("unit")),
                depth.group(0),
            ))
        elif (task.get("geometry") or {}).get("feature_type") == "rectangular_groove":
            contextual_depth = re.fullmatch(rf"\s*{_LENGTH}\s*[。.]?\s*", text, re.I)
            if contextual_depth:
                values.append((
                    "geometry.depth_mm",
                    _millimetres(
                        contextual_depth.group("value"), contextual_depth.group("unit")
                    ),
                    contextual_depth.group(0).strip(),
                ))

        diameter = re.search(
            rf"(?:通孔)?直径\s*(?:改为|改成|更正为|修正为|是|为|=|:|：)?\s*{_LENGTH}",
            text, re.I,
        )
        if diameter is None:
            diameter = re.search(
                rf"(?:开|加工|打|钻)(?:一个|一处)?\s*{_LENGTH}\s*(?:的)?通孔",
                text, re.I,
            )
        if diameter:
            diameter_mm = _millimetres(diameter.group("value"), diameter.group("unit"))
            values.extend([
                ("geometry.feature_type", "through_hole", diameter.group(0)),
                ("geometry.dimensions.diameter_mm", diameter_mm, diameter.group(0)),
                ("geometry.description", f"直径 {diameter_mm:g} mm 通孔", diameter.group(0)),
                ("geometry.through", True, diameter.group(0)),
            ])
        elif process == "cutting":
            values.append(("geometry.feature_type", "sheet_cut", text))

        if re.search(r"无分层|不得分层|no delamination", lowered):
            values.append(("quality_requirement", "no_delamination", _evidence(text, r"无分层|不得分层")))
        if re.search(r"无效率要求|效率无要求|不限时间", lowered):
            values.append(("efficiency_requirement", "none", _evidence(text, r"无效率要求|效率无要求|不限时间")))
        if "压缩空气" in text:
            values.append(("auxiliary", "compressed_air", "压缩空气"))
        elif "氮气" in text:
            values.append(("auxiliary", "nitrogen", "氮气"))
        if re.search(r"允许层切|允许分层切割|允许分层加工", text):
            values.append(("layer_cut_allowed", True, _evidence(text, r"允许(?:层切|分层切割|分层加工)")))
        elif re.search(r"不允许层切|禁止层切|不允许分层切割", text):
            values.append(("layer_cut_allowed", False, _evidence(text, r"不允许层切|禁止层切|不允许分层切割")))

        cut_length = re.search(
            rf"(?:切割(?:总)?长度|总切长|切长|轮廓总长)\s*(?:是|为|=|:|：)?\s*{_LENGTH}",
            text, re.I,
        ) or re.search(rf"{_LENGTH}\s*(?:直线|曲线|圆弧|圆形)", text, re.I)
        if cut_length:
            values.append((
                "cut_length_mm",
                _millimetres(cut_length.group("value"), cut_length.group("unit")),
                cut_length.group(0),
            ))
        contours = (("直线", "straight"), ("曲线", "curve"), ("圆弧", "arc"), ("圆形", "circle"))
        for marker, normalized in contours:
            if marker in text:
                values.append(("contour_type", normalized, marker))
                break
        return _deduplicate(values)

    @staticmethod
    def _ambiguities(message: str, task: dict[str, Any]) -> list[dict[str, Any]]:
        answer = message.strip(" 。；;")
        if answer in {"无", "没有", "无要求", "没有要求"} and task.get("process_intent") == "cutting":
            return [{
                "evidence": answer,
                "candidate_fields": ["efficiency_requirement", "auxiliary"],
                "reason": "ambiguous_short_answer",
            }]
        return []


def prepare_task_context(message: str, working_context: dict[str, Any]) -> TaskIntakeResult:
    return HybridTaskFieldExtractionService().prepare(message, working_context)


def _blocking_fields(task: dict[str, Any]) -> list[str]:
    geometry = task.get("geometry") or {}
    if geometry.get("feature_type") == "rectangular_groove" \
            and geometry.get("depth_mm") is None and not geometry.get("through"):
        return ["geometry.depth_mm"]
    return []


def _read_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _write_path(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for key in parts[:-1]:
        current = current.setdefault(key, {})
    current[parts[-1]] = value


def _deep_merge_copy(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = {**current}
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merged[key] = _deep_merge_copy(current[key], value)
        else:
            merged[key] = value
    return merged


def _millimetres(value: str, unit: str) -> float:
    factors = {"mm": 1.0, "毫米": 1.0, "cm": 10.0, "厘米": 10.0,
               "um": 0.001, "μm": 0.001, "µm": 0.001}
    return float(value) * factors[unit]


def _evidence(message: str, pattern: str) -> str:
    found = re.search(pattern, message, re.I)
    return found.group(0) if found else message


def _deduplicate(values: list[tuple[str, Any, str]]) -> list[tuple[str, Any, str]]:
    result: dict[str, tuple[str, Any, str]] = {}
    for item in values:
        result[item[0]] = item
    return list(result.values())
