from __future__ import annotations

import math
import re
from typing import Any

from ultrafast_domain.domain_packs import load_domain_pack
from ultrafast_domain.trial.models import TrialAssessment, TrialDecision, TrialMode, TrialPlanDraft


SIMPLE_REASON_FLAGS = {
    "first_material": "first_material",
    "first_equipment_revision": "first_equipment_revision",
    "first_wavelength_or_pulse_width": "first_wavelength_or_pulse_width",
    "complex_geometry": "complex_geometry",
    "expensive_material": "expensive_material",
    "long_full_trial": "long_full_trial",
    "high_risk": "high_risk",
}


def assess_trial_need(
    task_spec: dict[str, Any],
    *,
    evidence_status: str = "insufficient",
    approved_prior_count: int = 0,
    similar_case_count: int = 0,
    valid_sample_count: int = 0,
    equipment_revision_unchanged: bool = False,
) -> TrialAssessment:
    exact_repeat = bool(task_spec.get("exact_repeat"))
    complete_qualified_record = bool(task_spec.get("complete_qualified_record"))
    user_allows_skip = bool(task_spec.get("user_allows_skip"))
    if exact_repeat and complete_qualified_record and equipment_revision_unchanged and user_allows_skip:
        return TrialAssessment(
            recommended_mode=TrialMode.SKIP,
            allowed_modes=(TrialMode.SKIP, TrialMode.SIMPLE, TrialMode.FULL),
            reasons=("exact_repeat_with_complete_qualified_record",),
            risk_level="low",
        )

    reasons = [reason for flag, reason in SIMPLE_REASON_FLAGS.items() if task_spec.get(flag)]
    if approved_prior_count == 0:
        reasons.append("no_approved_process_prior")
    if evidence_status not in {"sufficient", "approved"}:
        reasons.append("insufficient_evidence")
    if valid_sample_count < 10:
        reasons.append("validated_samples_below_10")
    high_risk = bool(reasons)
    full_path_required = bool(task_spec.get("full_path_validation_required"))
    highly_matched = (
        approved_prior_count > 0
        and evidence_status in {"sufficient", "approved"}
        and similar_case_count > 0
        and equipment_revision_unchanged
    )
    if full_path_required and highly_matched and not task_spec.get("high_risk"):
        return TrialAssessment(
            recommended_mode=TrialMode.FULL,
            allowed_modes=(TrialMode.SIMPLE, TrialMode.FULL),
            reasons=("full_path_accumulation_requires_validation", "matched_prior_case_and_equipment"),
            risk_level="medium",
        )
    return TrialAssessment(
        recommended_mode=TrialMode.SIMPLE,
        allowed_modes=(TrialMode.SIMPLE, TrialMode.FULL),
        reasons=tuple(dict.fromkeys(reasons or ["new_or_unverified_task"])),
        risk_level="high" if high_risk else "medium",
    )


def select_trial_mode(assessment: TrialAssessment | dict[str, Any], selected: str) -> TrialMode:
    if isinstance(assessment, dict):
        allowed = tuple(TrialMode(value) for value in assessment.get("allowed_modes", []))
    else:
        allowed = assessment.allowed_modes
    mode = TrialMode(selected)
    if mode not in allowed:
        raise ValueError(f"trial mode is not allowed by the current assessment: {mode.value}")
    return mode


def design_trial_plan(
    task_id: str,
    task_spec: dict[str, Any],
    trial_mode: TrialMode | str,
    machine_bounds: dict[str, list[float | int]],
    domain_pack_name: str | None = None,
    approved_parameter_candidates: list[dict[str, float | int]] | None = None,
) -> TrialPlanDraft:
    mode = TrialMode(trial_mode)
    if mode == TrialMode.SKIP:
        return TrialPlanDraft(
            task_id=task_id,
            trial_mode=mode,
            representative_geometry={"type": "none", "reason": "verified repeat task"},
            parameter_matrix=[],
            measurement_plan={"required": False},
            acceptance_criteria=[],
            stop_conditions=[],
            status="skipped",
        )
    pack = load_domain_pack(domain_pack_name) if domain_pack_name else None
    template = pack.trial_templates.get(mode.value, {}) if pack else {}
    representative = {
        "type": template.get("representative_geometry") or _representative_geometry(task_spec, mode),
        "full_geometry": mode == TrialMode.FULL,
        "source": f"domain_pack:{domain_pack_name}" if pack else "process_type_rule",
    }
    parameter_matrix = list(approved_parameter_candidates or [])
    metrics = list(pack.quality_metrics) if pack else list(task_spec.get("quality_metrics") or [])
    measurement = {
        "required": True,
        "metrics": metrics,
        "templates": pack.measurement_templates if pack else {},
        "traceability_required": True,
    }
    criteria = _acceptance_criteria(task_spec.get("targets") or {}, metrics)
    stop_conditions = _stop_conditions(task_spec)
    warnings = []
    if not parameter_matrix:
        warnings.append("parameter matrix is empty because no parameter tool output was approved")
    return TrialPlanDraft(
        task_id=task_id,
        trial_mode=mode,
        representative_geometry=representative,
        parameter_matrix=parameter_matrix,
        measurement_plan=measurement,
        acceptance_criteria=criteria,
        stop_conditions=stop_conditions,
        warnings=warnings,
    )


def evaluate_trial_result(
    acceptance_criteria: list[dict[str, Any]],
    measurements: dict[str, Any],
    defects: list[dict[str, Any]] | dict[str, Any],
    monitoring_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    missing: list[str] = []
    defect_values = defects if isinstance(defects, list) else [
        {"name": key, "severity": value} for key, value in defects.items()
    ]
    for defect in defect_values:
        if str(defect.get("severity", "")).lower() in {"critical", "fail", "severe"}:
            failures.append(f"critical_defect:{defect.get('name', 'unknown')}")
    if (monitoring_summary or {}).get("abnormal"):
        failures.append("abnormal_monitoring")
    for criterion in acceptance_criteria:
        if criterion.get("type") == "critical_defects_absent":
            continue
        metric = criterion.get("metric")
        if not metric:
            continue
        if metric not in measurements or measurements[metric] is None:
            if criterion.get("required", True):
                missing.append(metric)
            continue
        if "value" not in criterion:
            continue
        observed = float(measurements[metric])
        expected = float(criterion["value"])
        operator = criterion.get("operator")
        passed = {
            "<=": observed <= expected,
            ">=": observed >= expected,
            "<": observed < expected,
            ">": observed > expected,
            "==": math.isclose(observed, expected),
        }.get(operator, False)
        if not passed:
            failures.append(f"criterion_failed:{metric}")
    if failures:
        decision = TrialDecision.FAIL
        unlocked = False
    elif missing:
        decision = TrialDecision.CONDITIONAL_PASS
        unlocked = False
    else:
        decision = TrialDecision.PASS
        unlocked = True
    return {
        "decision": decision.value,
        "quality_status": decision.value,
        "formal_process_unlocked": unlocked,
        "failures": failures,
        "missing_measurements": missing,
    }


def _representative_geometry(task_spec: dict[str, Any], mode: TrialMode) -> str:
    process = str(task_spec.get("process_type") or "").lower()
    if mode == TrialMode.FULL:
        return "full_target_geometry_and_complete_toolpath"
    if any(token in process for token in ("drill", "hole", "tgv", "钻孔", "孔")):
        return "single_hole_or_3x3_hole_array"
    if any(token in process for token in ("cut", "切割")):
        return "straight_line_small_circle_or_short_arc"
    if any(token in process for token in ("texture", "surface", "织构", "表面")):
        return "small_groove_dot_or_stripe_patch"
    return "single_track_rectangle_step_or_small_pocket"


def _parameter_matrix(bounds: dict[str, Any], *, full: bool) -> list[dict[str, float | int]]:
    usable = []
    for name, value in sorted(bounds.items()):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        try:
            lower, upper = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            continue
        if lower <= upper:
            usable.append((name, lower, upper))
    if not usable:
        return []
    fractions = (
        (0.1, 0.3, 0.5, 0.7, 0.9)
        if not full
        else (0.05, 0.1625, 0.275, 0.3875, 0.5, 0.6125, 0.725, 0.8375, 0.95)
    )
    rows = []
    for fraction in fractions:
        row = {}
        for name, lower, upper in usable:
            value = lower + fraction * (upper - lower)
            row[name] = max(1, int(round(value))) if name == "passes" else float(value)
        rows.append(row)
    return rows


def _acceptance_criteria(targets: dict[str, Any], metrics: list[str]) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = [{"type": "critical_defects_absent", "required": True}]
    for key, raw in targets.items():
        if isinstance(raw, dict):
            if raw.get("max") is not None:
                criteria.append({"metric": key, "operator": "<=", "value": raw["max"], "unit": raw.get("unit"), "required": True})
            if raw.get("min") is not None:
                criteria.append({"metric": key, "operator": ">=", "value": raw["min"], "unit": raw.get("unit"), "required": True})
            continue
        match = re.match(r"(.+?)_(max|min)_(.+)$", key)
        if match and isinstance(raw, (int, float)):
            metric, direction, unit = match.groups()
            criteria.append({"metric": f"{metric}_{unit}", "operator": "<=" if direction == "max" else ">=", "value": raw, "unit": unit, "required": True})
    declared = {item.get("metric") for item in criteria}
    for metric in metrics:
        if metric not in declared:
            criteria.append({"metric": metric, "required": False, "source": "domain_pack"})
    return criteria


def _stop_conditions(task_spec: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = [
        "energy_drift",
        "depth_deviation",
        "temperature_anomaly",
        "crack_growth",
        "edge_chipping_exceeded",
        "online_monitoring_anomaly",
        "equipment_alarm",
        "processing_time_anomaly",
    ]
    thresholds = task_spec.get("stop_thresholds") or {}
    return [
        {
            "condition": name,
            "threshold": thresholds.get(name),
            "threshold_source": "task_or_equipment" if name in thresholds else "operator_or_equipment_interlock",
            "action": "stop_and_record",
        }
        for name in conditions
    ]
