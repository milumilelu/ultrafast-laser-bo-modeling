from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Iterable

from ultrafast_bo.application.governance import (
    BODatasetSliceService,
    BOReadinessAssessmentService,
)
from ultrafast_bo.application.lifecycle import BOModelRegistry
from ultrafast_bo.application.services import _BOCoreEngine, _numeric_bounds
from ultrafast_bo.domain.models import BOSample


class BORecommendationService:
    """Formal single BO application entrypoint with slicing, readiness, and version trace."""

    def __init__(
        self,
        *,
        dataset_slice: BODatasetSliceService | None = None,
        readiness: BOReadinessAssessmentService | None = None,
        engine: _BOCoreEngine | None = None,
        registry: BOModelRegistry | None = None,
    ):
        self.dataset_slice = dataset_slice or BODatasetSliceService()
        self.readiness = readiness or BOReadinessAssessmentService()
        self.engine = engine or _BOCoreEngine()
        self.registry = registry or BOModelRegistry()

    def recommend(
        self,
        task_spec: dict[str, Any],
        samples: Iterable[BOSample | dict[str, Any]],
        machine_context: dict[str, Any],
        approved_priors: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        material = task_spec.get("material")
        process_type = task_spec.get("process_type")
        target = task_spec.get("objective_metric")
        if not material or not process_type or not target:
            return self._blocked(
                "validation_failed",
                [name for name, value in (("material", material), ("process_type", process_type), ("objective_metric", target)) if not value],
                task_spec,
            )
        scoped, slice_report = self.dataset_slice.select(
            samples,
            material=str(material),
            process_type=str(process_type),
            equipment_profile_id=task_spec.get("equipment_profile_id") or machine_context.get("equipment_profile_id"),
            target_metric=str(target),
            measurement_method=task_spec.get("measurement_method"),
            process_stage=task_spec.get("process_stage"),
            feature_schema_version=task_spec.get("feature_schema_version", "1.0"),
        )
        bounds = _numeric_bounds(machine_context.get("machine_bounds") or {})
        readiness = self.readiness.assess(
            scoped, target_metric=str(target), parameter_bounds=bounds,
            validation_metrics=task_spec.get("validation_metrics"),
        )
        dataset = self.registry.register_dataset(
            slice_report.selected_sample_ids,
            {
                "material": material,
                "process_type": process_type,
                "equipment_profile_id": task_spec.get("equipment_profile_id") or machine_context.get("equipment_profile_id"),
                "target_metric": target,
            },
            task_spec.get("feature_schema_version", "1.0"),
        )
        engine_result = self.engine.recommend(
            {**task_spec, "_governed_model_status": readiness.model_status},
            scoped, machine_context, approved_priors,
        )
        bo_run_id = f"bo_run_{uuid.uuid4().hex}"
        model_version = task_spec.get("model_version") or (
            "rule_based_baseline_v1" if not engine_result.get("bo_invoked") else f"ephemeral_gp_{dataset.content_hash[:12]}"
        )
        result = {
            "bo_run_id": bo_run_id,
            "status": "blocked" if engine_result.get("model_status") == "blocked" else "ready",
            "model_status": readiness.model_status if engine_result.get("model_status") != "blocked" else "blocked",
            "engine_model_status": engine_result.get("model_status"),
            "task_scope": {"material": material, "process_type": process_type, "target_metric": target},
            "dataset_slice_report": slice_report.to_dict(),
            "readiness_report": readiness.to_dict(),
            "recommended_parameters": engine_result.get("recommended_parameters") or {},
            "predictions": engine_result.get("prediction") or {},
            "uncertainty": (engine_result.get("prediction") or {}).get("uncertainty"),
            "warnings": [*readiness.warnings, *(engine_result.get("warnings") or [])],
            "blocking_reasons": [*readiness.blocking_reasons] if engine_result.get("model_status") != "blocked" else engine_result.get("warnings", []),
            "model_version": model_version,
            "dataset_version": dataset.dataset_version_id,
            "feature_schema_version": task_spec.get("feature_schema_version", "1.0"),
            "objective_version": task_spec.get("objective_version", "1.0"),
            "acquisition_version": task_spec.get("acquisition_version", "ucb-1.0"),
            "random_seed": int(task_spec.get("random_seed", 42)),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "audit_trace": engine_result.get("audit_trace") or [],
            "bo_invoked": bool(engine_result.get("bo_invoked")),
            "acquisition": engine_result.get("acquisition") or {},
            "sample_count": len(scoped),
            "machine_bounds_revision": machine_context.get("revision_id"),
            "knowledge_approval_ids": engine_result.get("knowledge_approval_ids") or [],
        }
        trace = {
            "bo_run_id": bo_run_id,
            "training_sample_ids": slice_report.selected_sample_ids,
            "dataset_version": dataset.dataset_version_id,
            "model_version": model_version,
            "feature_schema_version": result["feature_schema_version"],
            "objective_version": result["objective_version"],
            "acquisition_version": result["acquisition_version"],
            "random_seed": result["random_seed"],
            "code_commit": task_spec.get("code_version", "unknown"),
            "equipment_profile_version": machine_context.get("revision_id") or "unknown",
            "approved_prior_versions": [str(p.get("version") or p.get("approval_id")) for p in (approved_priors or [])],
            "result": result,
        }
        self.registry.record_run(trace)
        return result

    def replay_bo_run(self, bo_run_id: str) -> dict[str, Any]:
        return self.registry.replay_bo_run(bo_run_id)["result"]

    @staticmethod
    def _blocked(code: str, missing: list[str], task_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "bo_run_id": f"bo_run_{uuid.uuid4().hex}", "status": "blocked", "model_status": "blocked",
            "task_scope": dict(task_spec), "dataset_slice_report": None, "readiness_report": None,
            "recommended_parameters": {}, "predictions": {}, "uncertainty": None, "warnings": [],
            "blocking_reasons": [f"missing required field: {name}" for name in missing],
            "error_code": code, "model_version": None, "dataset_version": None,
            "feature_schema_version": task_spec.get("feature_schema_version", "1.0"),
            "objective_version": task_spec.get("objective_version", "1.0"),
            "acquisition_version": task_spec.get("acquisition_version", "ucb-1.0"),
            "random_seed": int(task_spec.get("random_seed", 42)),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
