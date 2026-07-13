from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, Iterable

from ultrafast_bo.application.formal_service import BORecommendationService
from ultrafast_bo.domain.models import BOSample


class LegacyBOCompatibilityAdapter:
    """Legacy field mapping around the single formal service; no BO logic lives here."""

    def __init__(self, service: BORecommendationService | None = None):
        self.service = service or BORecommendationService()

    def recommend(self, task_spec: dict[str, Any], samples: Iterable[BOSample | dict[str, Any]], machine_context: dict[str, Any], approved_priors: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        values = list(samples)
        task = dict(task_spec)
        task.setdefault("material", _first(values, "material") or "unspecified")
        task.setdefault("process_type", _first(values, "process_type") or "unspecified")
        task.setdefault("objective_metric", _first_target(values) or "objective_score")
        task.setdefault("feature_schema_version", "1.0")
        normalized = [_with_scope(value, task) for value in values]
        formal = self.service.recommend(task, normalized, machine_context, approved_priors)
        return {
            "model_status": formal.get("engine_model_status") or formal.get("model_status"), "sample_count": formal.get("sample_count", 0),
            "recommended_parameters": formal.get("recommended_parameters") or {},
            "prediction": formal.get("predictions") or {}, "acquisition": formal.get("acquisition") or {},
            "bo_invoked": formal.get("bo_invoked", False),
            "machine_bounds_revision": formal.get("machine_bounds_revision"),
            "knowledge_approval_ids": formal.get("knowledge_approval_ids") or [],
            "warnings": formal.get("warnings") or [], "audit_trace": formal.get("audit_trace") or [],
            "bo_run_id": formal.get("bo_run_id"), "dataset_version": formal.get("dataset_version"),
            "model_version": formal.get("model_version"), "readiness_report": formal.get("readiness_report"),
            "dataset_slice_report": formal.get("dataset_slice_report"),
        }


def _first(values: list[Any], name: str) -> Any:
    for value in values:
        item = getattr(value, name, None) if isinstance(value, BOSample) else value.get(name)
        if item:
            return item
    return None


def _first_target(values: list[Any]) -> str | None:
    for value in values:
        metrics = value.y_metrics if isinstance(value, BOSample) else value.get("y_metrics") or value.get("y_metrics_json") or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except json.JSONDecodeError:
                metrics = {}
        if metrics:
            return next(iter(metrics))
    return None


def _with_scope(value: BOSample | dict[str, Any], task: dict[str, Any]) -> BOSample | dict[str, Any]:
    if isinstance(value, BOSample):
        return replace(value, material=value.material or task["material"], process_type=value.process_type or task["process_type"])
    mapped = dict(value)
    mapped.setdefault("material", task["material"])
    mapped.setdefault("process_type", task["process_type"])
    mapped.setdefault("feature_schema_version", task["feature_schema_version"])
    return mapped
