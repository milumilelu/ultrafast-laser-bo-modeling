from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ultrafast_bo.application.services import RecommendationService


def load_agent_export(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def recommend_from_agent_export(
    task_spec: dict[str, Any],
    training_csv_path: str | Path,
    machine_context: dict[str, Any],
    approved_priors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    samples = load_agent_export(training_csv_path)
    result = RecommendationService().recommend(
        task_spec=task_spec,
        samples=samples,
        machine_context=machine_context,
        approved_priors=approved_priors or [],
    )
    result["training_csv_path"] = str(training_csv_path)
    result["compatibility_adapter"] = "agent_export_v1"
    return result
