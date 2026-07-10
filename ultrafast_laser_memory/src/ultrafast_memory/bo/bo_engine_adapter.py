from __future__ import annotations

from pathlib import Path

from ultrafast_bo.compatibility.agent_export import recommend_from_agent_export
from ultrafast_memory.equipment.bounds import build_machine_bounds


def call_bo_recommendation(task_spec: dict, training_csv_path: str) -> dict:
    spec = dict(task_spec)
    machine_context = spec.pop("machine_context", None)
    explicit_bounds = spec.pop("machine_bounds", None)
    if machine_context is None and explicit_bounds:
        machine_context = {
            "active": True,
            "machine_bounds": explicit_bounds,
            "revision_id": spec.pop("equipment_revision", "task-override"),
        }
    if machine_context is None:
        machine_context = build_machine_bounds()
    approved_priors = spec.pop("approved_priors", [])
    return recommend_from_agent_export(
        task_spec=spec,
        training_csv_path=Path(training_csv_path),
        machine_context=machine_context,
        approved_priors=approved_priors,
    )
