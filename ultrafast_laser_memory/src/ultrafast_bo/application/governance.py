from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Iterable

import numpy as np

from ultrafast_bo.domain.models import BOModelStatus, BOSample


@dataclass(slots=True)
class DatasetSliceReport:
    selected_sample_ids: list[str]
    excluded_counts_by_reason: dict[str, int]
    material: str
    process_type: str
    equipment_scope: str | None
    target_metric: str | None
    measurement_scope: str | None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BODatasetSliceService:
    """The only strict task-scoped sample selector used by the formal BO service."""

    def select(
        self,
        samples: Iterable[BOSample | dict[str, Any]],
        *,
        material: str,
        process_type: str,
        equipment_profile_id: str | None = None,
        target_metric: str | None = None,
        measurement_method: str | None = None,
        process_stage: str | None = None,
        feature_schema_version: str | None = None,
    ) -> tuple[list[BOSample], DatasetSliceReport]:
        selected: list[BOSample] = []
        excluded: Counter[str] = Counter()
        for index, raw in enumerate(samples):
            sample = raw if isinstance(raw, BOSample) else _coerce_sample(raw, index)
            reason = self._exclusion_reason(
                sample,
                material=material,
                process_type=process_type,
                equipment_profile_id=equipment_profile_id,
                target_metric=target_metric,
                measurement_method=measurement_method,
                process_stage=process_stage,
                feature_schema_version=feature_schema_version,
            )
            if reason:
                excluded[reason] += 1
            else:
                selected.append(sample)
        warnings = []
        if equipment_profile_id is None:
            warnings.append("equipment scope was not supplied; only samples without a conflicting equipment id were accepted")
        report = DatasetSliceReport(
            selected_sample_ids=[s.sample_id for s in selected],
            excluded_counts_by_reason=dict(sorted(excluded.items())),
            material=material,
            process_type=process_type,
            equipment_scope=equipment_profile_id,
            target_metric=target_metric,
            measurement_scope=measurement_method,
            warnings=warnings,
        )
        return selected, report

    @staticmethod
    def _exclusion_reason(sample: BOSample, **scope: Any) -> str | None:
        if sample.material != scope["material"]:
            return "material_mismatch"
        if sample.process_type != scope["process_type"]:
            return "process_type_mismatch"
        if not sample.valid_for_training:
            return "not_approved_for_training"
        if sample.source_type in {"ocr", "rag", "llm", "vision"}:
            return "unapproved_source_type"
        if sample.run_status != "completed" or sample.abnormal or sample.alarms:
            return "abnormal_or_incomplete_run"
        equipment = scope["equipment_profile_id"]
        if equipment and sample.equipment_profile_id not in {None, equipment} and equipment not in sample.equipment_compatible_with:
            return "equipment_mismatch"
        target = scope["target_metric"]
        if target and target not in sample.y_metrics:
            return "target_missing"
        method = scope["measurement_method"]
        if method and sample.measurement_method not in {None, method} and not sample.measurement_standardized:
            return "measurement_method_mismatch"
        stage = scope["process_stage"]
        if stage and sample.process_stage not in {None, stage}:
            return "process_stage_mismatch"
        schema = scope["feature_schema_version"]
        if schema and sample.feature_schema_version != schema:
            return "feature_schema_mismatch"
        if not sample.x_parameters:
            return "parameters_missing"
        return None


@dataclass(slots=True)
class BOEligibilityReport:
    eligible: bool
    blocking_reasons: list[str]
    warnings: list[str]
    normalized_parameters: dict[str, float]
    normalized_measurements: dict[str, float]
    source_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BOEligibilityService:
    """Feedback remains a candidate until this report passes and approval is recorded."""

    def assess(self, candidate: dict[str, Any]) -> BOEligibilityReport:
        reasons: list[str] = []
        warnings: list[str] = []
        recommendation_id = candidate.get("recommendation_id")
        task_id = candidate.get("task_id")
        actual = candidate.get("machine_actual_parameters")
        measurements = candidate.get("measurements")
        if not recommendation_id or not task_id:
            reasons.append("task_and_recommendation_trace_required")
        if not actual:
            reasons.append("machine_actual_parameters_required")
        if not measurements:
            reasons.append("target_measurements_required")
        if candidate.get("run_status") != "completed":
            reasons.append("run_not_completed")
        if candidate.get("alarms"):
            reasons.append("blocking_alarm_present")
        if not candidate.get("measurement_method"):
            reasons.append("measurement_method_unknown")
        if candidate.get("out_of_bounds"):
            reasons.append("actual_parameters_out_of_bounds")
        if candidate.get("manual_exclusion"):
            reasons.append("manually_excluded")
        if candidate.get("duplicate") and not candidate.get("replicate_id"):
            reasons.append("duplicate_without_replicate_id")
        parameters = _numeric(actual or {})
        metrics = _numeric(measurements or {})
        if actual and len(parameters) != len(actual):
            reasons.append("parameter_unit_or_value_invalid")
        if measurements and not metrics:
            reasons.append("measurement_unit_or_value_invalid")
        if not candidate.get("cam_applied_parameters"):
            warnings.append("CAM-applied parameters were not supplied; provenance is incomplete")
        sources = [str(value) for value in (
            candidate.get("run_id"), recommendation_id, task_id, candidate.get("raw_feedback_id")
        ) if value]
        return BOEligibilityReport(not reasons, reasons, warnings, parameters, metrics, sources)


@dataclass(slots=True)
class BOReadinessReport:
    model_status: str
    valid_sample_count: int
    complete_target_count: int
    complete_feature_count: int
    effective_dimension: int
    parameter_coverage: dict[str, float]
    replicate_count: int
    noise_estimate: float | None
    validation_metrics: dict[str, Any]
    uncertainty_calibrated: bool
    blocking_reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BOReadinessAssessmentService:
    def assess(
        self,
        samples: Iterable[BOSample],
        *,
        target_metric: str,
        parameter_bounds: dict[str, list[float]],
        validation_metrics: dict[str, Any] | None = None,
    ) -> BOReadinessReport:
        rows = list(samples)
        features = sorted(parameter_bounds)
        target_rows = [s for s in rows if target_metric in s.y_metrics]
        complete = [s for s in target_rows if all(name in s.x_parameters for name in features)]
        coverage = {
            name: _coverage([s.x_parameters[name] for s in complete if name in s.x_parameters], parameter_bounds[name])
            for name in features
        }
        groups: dict[tuple[float, ...], list[float]] = {}
        for sample in complete:
            key = tuple(round(sample.x_parameters[name], 9) for name in features)
            groups.setdefault(key, []).append(sample.y_metrics[target_metric])
        replicate_groups = [values for values in groups.values() if len(values) > 1]
        replicate_count = sum(len(values) - 1 for values in replicate_groups)
        noise = None
        if replicate_groups:
            variances = [float(np.var(values, ddof=1)) for values in replicate_groups]
            noise = float(math.sqrt(max(float(np.mean(variances)), 0.0)))
        metrics = dict(validation_metrics or {})
        calibrated = bool(metrics.get("prediction_interval_coverage") is not None and metrics.get("uncertainty_calibration_error") is not None)
        warnings: list[str] = []
        blocking: list[str] = []
        dimension = sum(1 for lo, hi in parameter_bounds.values() if float(hi) > float(lo))
        if not features:
            blocking.append("no_model_features")
        if not target_rows:
            warnings.append("no_complete_target; cold-start governance is required")
        if len(complete) < max(5, dimension + 2):
            warnings.append("too_few_complete_samples_for_effective_dimension")
        if dimension and len(complete) < 3 * dimension:
            warnings.append("high_dimension_small_sample")
        if coverage and min(coverage.values()) < 0.2:
            warnings.append("poor_parameter_coverage")
        if replicate_count == 0:
            warnings.append("noise_not_estimable_without_replicates")
        if blocking:
            status = BOModelStatus.BLOCKED.value
        elif len(complete) < max(10, 3 * max(dimension, 1)) or min(coverage.values(), default=0) < 0.25:
            status = BOModelStatus.RULE_BASED_COLD_START.value
        elif not calibrated or len(complete) < max(30, 6 * max(dimension, 1)):
            status = BOModelStatus.HYBRID_RULE_BO.value
        else:
            status = BOModelStatus.DATA_DRIVEN_BO.value
        return BOReadinessReport(
            status, len(rows), len(target_rows), len(complete), dimension, coverage,
            replicate_count, noise, metrics, calibrated, blocking, warnings,
        )


def _coerce_sample(raw: dict[str, Any], index: int) -> BOSample:
    fields = BOSample.__dataclass_fields__
    kwargs = {name: raw[name] for name in fields if name in raw}
    kwargs.setdefault("sample_id", str(raw.get("sample_id") or f"sample-{index}"))
    kwargs.setdefault("x_parameters", _numeric(raw.get("x_parameters") or raw.get("x_parameters_json") or {}))
    kwargs.setdefault("y_metrics", _numeric(raw.get("y_metrics") or raw.get("y_metrics_json") or {}))
    if isinstance(kwargs.get("equipment_compatible_with"), list):
        kwargs["equipment_compatible_with"] = tuple(kwargs["equipment_compatible_with"])
    if isinstance(kwargs.get("alarms"), list):
        kwargs["alarms"] = tuple(kwargs["alarms"])
    return BOSample(**kwargs)


def _numeric(value: Any) -> dict[str, float]:
    if isinstance(value, str):
        import json
        value = json.loads(value)
    result = {}
    for name, raw in (value or {}).items():
        if isinstance(raw, bool) or raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result[str(name)] = number
    return result


def _coverage(values: list[float], bounds: list[float]) -> float:
    lower, upper = map(float, bounds)
    if not values or upper <= lower:
        return 1.0 if values else 0.0
    return max(0.0, min(1.0, (max(values) - min(values)) / (upper - lower)))
