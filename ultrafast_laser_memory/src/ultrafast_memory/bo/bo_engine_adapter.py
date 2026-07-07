from __future__ import annotations


def call_bo_recommendation(task_spec: dict, training_csv_path: str) -> dict:
    return {
        "model_status": "not_connected",
        "task_spec": task_spec,
        "training_csv_path": training_csv_path,
    }
