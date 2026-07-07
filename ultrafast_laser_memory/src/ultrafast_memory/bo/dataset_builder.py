from __future__ import annotations

import csv
import json
from pathlib import Path

from ultrafast_memory.core.config import resolve_path
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.validation.bo_eligibility import evaluate_run


CSV_COLUMNS = [
    "sample_id",
    "run_id",
    "material",
    "process_type",
    "pulse_width_fs",
    "frequency_kHz",
    "laser_power_W",
    "scan_speed_mm_s",
    "passes",
    "focus_offset_um",
    "hatch_spacing_um",
    "layer_step_um",
    "Ra_nm",
    "Sa_nm",
    "depth_um",
    "form_error_um",
    "removal_rate_um3_s",
    "graphitization_score",
    "valid_for_training",
    "invalid_reason",
]


def _metric_column(metric_name: str, metric_unit: str) -> str:
    name = metric_name.strip()
    unit = metric_unit.replace("/", "_")
    if name in {"Ra", "Sa"}:
        return f"{name}_{unit}"
    return f"{name}_{unit}"


def export_bo_dataset(export_path: str | Path | None = None) -> dict:
    path = Path(export_path) if export_path else resolve_path("data/exports/bo_training_samples.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with get_connection() as conn:
        runs = conn.execute("SELECT * FROM process_run ORDER BY run_id").fetchall()
        for run in runs:
            valid, reason = evaluate_run(conn, run["run_id"])
            recipe = conn.execute("SELECT * FROM process_recipe WHERE recipe_id = ?", (run["recipe_id"],)).fetchone()
            task = conn.execute("SELECT * FROM process_task WHERE task_id = ?", (run["task_id"],)).fetchone()
            if not recipe or not task:
                continue
            measurements = conn.execute(
                "SELECT * FROM measurement_record WHERE run_id = ? AND valid_flag = 1",
                (run["run_id"],),
            ).fetchall()
            y_metrics = {_metric_column(m["metric_name"], m["metric_unit"]): m["metric_value"] for m in measurements}
            x_params = {
                "pulse_width_fs": recipe["pulse_width_fs"],
                "frequency_kHz": recipe["frequency_kHz"],
                "laser_power_W": recipe["laser_power_W"],
                "scan_speed_mm_s": recipe["scan_speed_mm_s"],
                "passes": recipe["passes"],
                "focus_offset_um": recipe["focus_offset_um"],
                "hatch_spacing_um": recipe["hatch_spacing_um"],
                "layer_step_um": recipe["layer_step_um"],
            }
            sample_id = stable_id("sample", run["run_id"])
            conn.execute(
                """
                INSERT INTO bo_training_sample VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  material=excluded.material, process_type=excluded.process_type,
                  x_parameters_json=excluded.x_parameters_json, y_metrics_json=excluded.y_metrics_json,
                  constraints_json=excluded.constraints_json, valid_for_training=excluded.valid_for_training,
                  invalid_reason=excluded.invalid_reason, added_at=excluded.added_at
                """,
                (
                    sample_id,
                    run["run_id"],
                    task["material"],
                    recipe["process_type"],
                    json.dumps(x_params, ensure_ascii=False),
                    json.dumps(y_metrics, ensure_ascii=False),
                    None,
                    int(valid),
                    reason,
                    utc_now_iso(),
                ),
            )
            row = {column: "" for column in CSV_COLUMNS}
            row.update(
                {
                    "sample_id": sample_id,
                    "run_id": run["run_id"],
                    "material": task["material"],
                    "process_type": recipe["process_type"],
                    "valid_for_training": int(valid),
                    "invalid_reason": reason,
                    **x_params,
                    **y_metrics,
                }
            )
            rows.append(row)
        conn.commit()
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return {"export_path": str(path), "sample_count": len(rows)}
