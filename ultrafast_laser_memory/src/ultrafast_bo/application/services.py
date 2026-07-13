from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Iterable

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ultrafast_bo.domain.models import BOModelStatus, BORecommendation, BOSample


INTEGER_PARAMETERS = {"passes"}
LOWER_IS_BETTER = {"Sa_um", "Sa_nm", "Ra_um", "Ra_nm", "form_error_um", "graphitization_score", "defect_score"}
TARGET_PRIORITY = (
    "quality_score",
    "objective_score",
    "removal_rate_um3_s",
    "depth_um",
    "Sa_um",
    "Sa_nm",
    "Ra_um",
    "Ra_nm",
)


class BOBlockedError(ValueError):
    pass


class DatasetValidationService:
    def validate(self, samples: Iterable[BOSample | dict[str, Any]]) -> dict[str, Any]:
        accepted: list[BOSample] = []
        rejected: list[dict[str, str]] = []
        for index, raw in enumerate(samples):
            try:
                sample = raw if isinstance(raw, BOSample) else self._coerce(raw, index)
            except (TypeError, ValueError) as exc:
                rejected.append({"sample": str(index), "reason": str(exc)})
                continue
            if not sample.valid_for_training:
                rejected.append({"sample": sample.sample_id, "reason": "valid_for_training=false"})
                continue
            if not sample.x_parameters:
                rejected.append({"sample": sample.sample_id, "reason": "missing numeric x_parameters"})
                continue
            if not sample.y_metrics:
                rejected.append({"sample": sample.sample_id, "reason": "missing numeric y_metrics"})
                continue
            accepted.append(sample)
        return {"valid_samples": accepted, "rejected": rejected, "valid_count": len(accepted)}

    def _coerce(self, raw: dict[str, Any], index: int) -> BOSample:
        x = _numeric_mapping(raw.get("x_parameters") or raw.get("x_parameters_json") or {})
        y = _numeric_mapping(raw.get("y_metrics") or raw.get("y_metrics_json") or {})
        return BOSample(
            sample_id=str(raw.get("sample_id") or f"sample-{index}"),
            x_parameters=x,
            y_metrics=y,
            valid_for_training=_as_bool(raw.get("valid_for_training", True)),
            material=raw.get("material"),
            process_type=raw.get("process_type"),
        )


class BOStatusService:
    def __init__(self, cold_start_max_samples: int = 9, hybrid_max_samples: int = 29):
        self.cold_start_max_samples = cold_start_max_samples
        self.hybrid_max_samples = hybrid_max_samples

    def status_for_count(self, valid_sample_count: int) -> BOModelStatus:
        if valid_sample_count <= self.cold_start_max_samples:
            return BOModelStatus.RULE_BASED_COLD_START
        if valid_sample_count <= self.hybrid_max_samples:
            return BOModelStatus.HYBRID_RULE_BO
        return BOModelStatus.DATA_DRIVEN_BO

    def get_status(self, samples: Iterable[BOSample | dict[str, Any]]) -> dict[str, Any]:
        validation = DatasetValidationService().validate(samples)
        status = self.status_for_count(validation["valid_count"])
        return {
            "model_status": status.value,
            "valid_sample_count": validation["valid_count"],
            "rejected_sample_count": len(validation["rejected"]),
        }


class OfflineModelingService:
    def fit_and_recommend(
        self,
        samples: list[BOSample],
        bounds: dict[str, list[float]],
        task_spec: dict[str, Any],
        model_status: BOModelStatus,
        candidate_count: int = 256,
    ) -> dict[str, Any]:
        target = self._select_target(samples, task_spec.get("objective_metric"))
        feature_names = self._select_features(samples, bounds, target)
        model_rows = [sample for sample in samples if target in sample.y_metrics and all(name in sample.x_parameters for name in feature_names)]
        if len(model_rows) < 5:
            raise BOBlockedError("at least 5 complete numeric rows are required for surrogate modeling")
        x = np.asarray([[sample.x_parameters[name] for name in feature_names] for sample in model_rows], dtype=float)
        raw_y = np.asarray([sample.y_metrics[target] for sample in model_rows], dtype=float)
        sign = -1.0 if target in LOWER_IS_BETTER else 1.0
        y = raw_y * sign
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(
            length_scale=np.ones(len(feature_names)),
            length_scale_bounds=(1e-3, 1e3),
            nu=2.5,
        ) + WhiteKernel(
            noise_level=1e-5, noise_level_bounds=(1e-8, 1e0)
        )
        pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "gpr",
                    GaussianProcessRegressor(
                        kernel=kernel,
                        normalize_y=True,
                        random_state=int(task_spec.get("random_seed", 42)),
                        n_restarts_optimizer=max(0, int(task_spec.get("optimizer_restarts", 2))),
                    ),
                ),
            ]
        )
        pipeline.fit(x, y)
        candidates = self._candidates(bounds, feature_names, candidate_count, int(task_spec.get("random_seed", 42)))
        mean, std = pipeline.predict(candidates, return_std=True)
        beta = 1.25 if model_status == BOModelStatus.HYBRID_RULE_BO else 2.0
        ucb = mean + beta * std
        if model_status == BOModelStatus.HYBRID_RULE_BO:
            center_penalty = np.mean(np.abs(_normalize_candidates(candidates, feature_names, bounds) - 0.5), axis=1)
            score = 0.8 * _normalize_vector(ucb) - 0.2 * center_penalty
        else:
            score = ucb
        selected_index = int(np.argmax(score))
        selected = {
            name: _parameter_value(name, float(candidates[selected_index, idx]))
            for idx, name in enumerate(feature_names)
        }
        predicted_raw = float(mean[selected_index] * sign)
        return {
            "parameters": selected,
            "target_metric": target,
            "predicted_mean": predicted_raw,
            "predicted_std": float(std[selected_index]),
            "acquisition_score": float(score[selected_index]),
            "feature_names": feature_names,
            "model_rows": len(model_rows),
            "model": "GaussianProcessRegressor(Matern)",
        }

    def _select_target(self, samples: list[BOSample], requested: str | None) -> str:
        candidates = [requested] if requested else list(TARGET_PRIORITY)
        all_names = sorted({name for sample in samples for name in sample.y_metrics})
        candidates.extend(name for name in all_names if name not in candidates)
        for name in candidates:
            if name and sum(name in sample.y_metrics for sample in samples) >= 5:
                return name
        raise BOBlockedError("no objective metric has at least 5 numeric observations")

    def _select_features(
        self,
        samples: list[BOSample],
        bounds: dict[str, list[float]],
        target: str,
    ) -> list[str]:
        eligible_rows = [sample for sample in samples if target in sample.y_metrics]
        features = [
            name
            for name in sorted(bounds)
            if all(name in sample.x_parameters for sample in eligible_rows)
        ]
        if not features:
            raise BOBlockedError("no common numeric features overlap machine bounds and training samples")
        return features

    def _candidates(
        self,
        bounds: dict[str, list[float]],
        feature_names: list[str],
        candidate_count: int,
        seed: int,
    ) -> np.ndarray:
        rng = np.random.default_rng(seed)
        count = max(32, min(int(candidate_count), 4096))
        matrix = np.empty((count, len(feature_names)), dtype=float)
        for index, name in enumerate(feature_names):
            lower, upper = bounds[name]
            if math.isclose(lower, upper):
                matrix[:, index] = lower
            else:
                matrix[:, index] = rng.uniform(lower, upper, size=count)
        return matrix


class _BOCoreEngine:
    def __init__(
        self,
        validation: DatasetValidationService | None = None,
        status: BOStatusService | None = None,
        modeling: OfflineModelingService | None = None,
    ):
        self.validation = validation or DatasetValidationService()
        self.status = status or BOStatusService()
        self.modeling = modeling or OfflineModelingService()

    def recommend(
        self,
        task_spec: dict[str, Any],
        samples: Iterable[BOSample | dict[str, Any]],
        machine_context: dict[str, Any],
        approved_priors: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        prior_items = list(approved_priors or [])
        knowledge_gate = task_spec.get("knowledge_gate_decision") or {}
        gate_approval_ids = []
        reused_approval = knowledge_gate.get("reused_approval") or {}
        if reused_approval.get("approval_id"):
            gate_approval_ids.append(str(reused_approval["approval_id"]))
        literature_influences_bo = bool(
            task_spec.get("literature_parameters_used")
            or task_spec.get("knowledge_evidence_ids")
        )
        if literature_influences_bo and knowledge_gate.get("status") != "allowed":
            return BORecommendation(
                model_status=BOModelStatus.BLOCKED.value,
                sample_count=0,
                recommended_parameters={},
                prediction={},
                acquisition={"type": None, "score": None},
                bo_invoked=False,
                machine_bounds_revision=machine_context.get("revision_id"),
                warnings=["KnowledgeUseGate must allow literature-derived inputs before BO"],
                audit_trace=[{"step": "knowledge_use_gate", "status": knowledge_gate.get("status") or "missing"}],
            ).to_dict()
        machine_bounds = machine_context.get("machine_bounds") or {}
        if not machine_context.get("active") or not machine_bounds:
            return BORecommendation(
                model_status=BOModelStatus.BLOCKED.value,
                sample_count=0,
                recommended_parameters={},
                prediction={},
                acquisition={"type": None, "score": None},
                bo_invoked=False,
                machine_bounds_revision=machine_context.get("revision_id"),
                warnings=["active equipment bounds are required"],
                audit_trace=[{"step": "equipment_gate", "status": "blocked"}],
            ).to_dict()
        normalized_bounds = _numeric_bounds(machine_bounds)
        if not normalized_bounds:
            raise BOBlockedError("machine bounds contain no numeric ranges")
        bounded, approval_ids, prior_trace = _apply_approved_priors(
            normalized_bounds, prior_items
        )
        approval_ids = list(dict.fromkeys([*gate_approval_ids, *approval_ids]))
        validation = self.validation.validate(samples)
        valid_samples: list[BOSample] = validation["valid_samples"]
        governed_status = task_spec.get("_governed_model_status")
        try:
            model_status = BOModelStatus(governed_status) if governed_status else self.status.status_for_count(len(valid_samples))
        except ValueError as exc:
            raise BOBlockedError(f"unsupported governed model status: {governed_status}") from exc
        audit = [
            {
                "step": "dataset_validation",
                "status": "success",
                "valid_samples": len(valid_samples),
                "rejected_samples": len(validation["rejected"]),
            },
            *prior_trace,
        ]
        if model_status == BOModelStatus.BLOCKED:
            return BORecommendation(
                model_status=model_status.value, sample_count=len(valid_samples),
                recommended_parameters={}, prediction={}, acquisition={"type": None, "score": None},
                bo_invoked=False, machine_bounds_revision=machine_context.get("revision_id"),
                knowledge_approval_ids=approval_ids, warnings=["BO readiness assessment blocked modeling"],
                audit_trace=[*audit, {"step": "bo_mode", "status": model_status.value}],
            ).to_dict()
        if model_status == BOModelStatus.RULE_BASED_COLD_START:
            parameters = _cold_start_candidate(bounded)
            return BORecommendation(
                model_status=model_status.value,
                sample_count=len(valid_samples),
                recommended_parameters=parameters,
                prediction={"objective": None, "uncertainty": None},
                acquisition={"type": "conservative_rule", "score": None},
                bo_invoked=False,
                machine_bounds_revision=machine_context.get("revision_id"),
                knowledge_approval_ids=approval_ids,
                warnings=["insufficient validated samples for surrogate modeling"],
                audit_trace=[*audit, {"step": "bo_mode", "status": model_status.value}],
            ).to_dict()
        try:
            model = self.modeling.fit_and_recommend(
                valid_samples,
                bounded,
                task_spec,
                model_status,
                int(task_spec.get("candidate_count", 256)),
            )
        except BOBlockedError as exc:
            parameters = _cold_start_candidate(bounded)
            return BORecommendation(
                model_status=BOModelStatus.RULE_BASED_COLD_START.value,
                sample_count=len(valid_samples),
                recommended_parameters=parameters,
                prediction={"objective": None, "uncertainty": None},
                acquisition={"type": "conservative_rule", "score": None},
                bo_invoked=False,
                machine_bounds_revision=machine_context.get("revision_id"),
                knowledge_approval_ids=approval_ids,
                warnings=[f"surrogate fallback: {exc}"],
                audit_trace=[*audit, {"step": "bo_model", "status": "fallback", "reason": str(exc)}],
            ).to_dict()
        return BORecommendation(
            model_status=model_status.value,
            sample_count=len(valid_samples),
            recommended_parameters=model["parameters"],
            prediction={
                "metric": model["target_metric"],
                "mean": model["predicted_mean"],
                "uncertainty": model["predicted_std"],
            },
            acquisition={
                "type": "hybrid_ucb" if model_status == BOModelStatus.HYBRID_RULE_BO else "ucb",
                "score": model["acquisition_score"],
            },
            bo_invoked=True,
            machine_bounds_revision=machine_context.get("revision_id"),
            knowledge_approval_ids=approval_ids,
            audit_trace=[
                *audit,
                {"step": "bo_mode", "status": model_status.value},
                {
                    "step": "surrogate_model",
                    "status": "success",
                    "model": model["model"],
                    "rows": model["model_rows"],
                },
            ],
        ).to_dict()


class FeedbackService:
    def build_training_sample(
        self,
        sample_id: str,
        parameters: dict[str, Any],
        measurements: dict[str, Any],
        *,
        material: str | None = None,
        process_type: str | None = None,
        quality_valid: bool = True,
    ) -> dict[str, Any]:
        sample = BOSample(
            sample_id=sample_id,
            x_parameters=_numeric_mapping(parameters),
            y_metrics=_numeric_mapping(measurements),
            valid_for_training=quality_valid,
            material=material,
            process_type=process_type,
        )
        validation = DatasetValidationService().validate([sample])
        return {
            "accepted": bool(validation["valid_samples"]),
            "sample": asdict(sample),
            "rejected": validation["rejected"],
        }


class RecommendationService:
    """Deprecated legacy facade; all behavior is delegated to BORecommendationService."""

    def recommend(
        self,
        task_spec: dict[str, Any],
        samples: Iterable[BOSample | dict[str, Any]],
        machine_context: dict[str, Any],
        approved_priors: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter

        return LegacyBOCompatibilityAdapter().recommend(
            task_spec, samples, machine_context, approved_priors
        )


def _numeric_mapping(value: Any) -> dict[str, float]:
    if isinstance(value, str):
        import json

        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON mapping") from exc
    if not isinstance(value, dict):
        raise TypeError("expected a mapping")
    result = {}
    for key, item in value.items():
        if isinstance(item, bool) or item is None:
            continue
        try:
            numeric = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            result[str(key)] = numeric
    return result


def _numeric_bounds(bounds: dict[str, Any]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name, value in bounds.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        try:
            lower, upper = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(lower) and math.isfinite(upper) and lower <= upper:
            result[name] = [lower, upper]
    return result


def _cold_start_candidate(bounds: dict[str, list[float]]) -> dict[str, float | int]:
    candidate = {}
    for name, (lower, upper) in bounds.items():
        value = lower if math.isclose(lower, upper) else lower + 0.35 * (upper - lower)
        candidate[name] = _parameter_value(name, value)
    return candidate


def _parameter_value(name: str, value: float) -> float | int:
    if name in INTEGER_PARAMETERS:
        return max(1, int(round(value)))
    return float(value)


def _apply_approved_priors(
    bounds: dict[str, list[float]],
    priors: Iterable[dict[str, Any]],
) -> tuple[dict[str, list[float]], list[str], list[dict[str, Any]]]:
    result = {name: list(value) for name, value in bounds.items()}
    approval_ids: list[str] = []
    trace: list[dict[str, Any]] = []
    for prior in priors:
        approval_id = prior.get("approval_id")
        parameter = prior.get("parameter_name")
        if not approval_id:
            trace.append({"step": "knowledge_prior", "status": "ignored_unapproved"})
            continue
        if parameter not in result:
            trace.append({"step": "knowledge_prior", "status": "ignored_unknown_parameter", "approval_id": approval_id})
            continue
        try:
            lower = float(prior["lower_bound"])
            upper = float(prior["upper_bound"])
        except (KeyError, TypeError, ValueError):
            trace.append({"step": "knowledge_prior", "status": "ignored_invalid", "approval_id": approval_id})
            continue
        machine_lower, machine_upper = result[parameter]
        narrowed = [max(machine_lower, lower), min(machine_upper, upper)]
        if narrowed[0] > narrowed[1]:
            raise BOBlockedError(f"approved prior conflicts with machine bounds: {parameter}")
        result[parameter] = narrowed
        approval_ids.append(str(approval_id))
        trace.append({"step": "knowledge_prior", "status": "applied", "approval_id": approval_id, "parameter": parameter})
    return result, approval_ids, trace


def _normalize_vector(values: np.ndarray) -> np.ndarray:
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    if math.isclose(minimum, maximum):
        return np.zeros_like(values)
    return (values - minimum) / (maximum - minimum)


def _normalize_candidates(
    candidates: np.ndarray,
    feature_names: list[str],
    bounds: dict[str, list[float]],
) -> np.ndarray:
    result = np.zeros_like(candidates)
    for index, name in enumerate(feature_names):
        lower, upper = bounds[name]
        if math.isclose(lower, upper):
            result[:, index] = 0.5
        else:
            result[:, index] = (candidates[:, index] - lower) / (upper - lower)
    return result


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
