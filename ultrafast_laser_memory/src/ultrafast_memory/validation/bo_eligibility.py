from __future__ import annotations

import sqlite3


def evaluate_run(conn: sqlite3.Connection, run_id: str) -> tuple[bool, str]:
    run = conn.execute("SELECT * FROM process_run WHERE run_id = ?", (run_id,)).fetchone()
    if not run:
        return False, "missing run"
    if run["run_status"] != "completed":
        return False, "run_status is not completed"
    if run["abnormal_flag"]:
        return False, "run is abnormal"
    if (run["alarm_count"] or 0) > 0:
        return False, "run has alarms"
    recipe = conn.execute("SELECT * FROM process_recipe WHERE recipe_id = ?", (run["recipe_id"],)).fetchone()
    if not recipe:
        return False, "missing recipe"
    for field in ("laser_power_W", "frequency_kHz", "scan_speed_mm_s"):
        if recipe[field] is None:
            return False, f"missing recipe field {field}"
    task = conn.execute("SELECT * FROM process_task WHERE task_id = ?", (run["task_id"],)).fetchone()
    if not task or not task["material"]:
        return False, "missing material"
    if not recipe["process_type"]:
        return False, "missing process_type"
    measurements = conn.execute(
        "SELECT COUNT(*) AS n FROM measurement_record WHERE run_id = ? AND valid_flag = 1",
        (run_id,),
    ).fetchone()
    if not measurements or measurements["n"] < 1:
        return False, "missing valid measurement"
    return True, ""
