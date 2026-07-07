from __future__ import annotations

from pathlib import Path

from ultrafast_memory.db.session import get_connection


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_artifact (
    artifact_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    archived_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    file_size_bytes INTEGER,
    created_at TEXT,
    modified_at TEXT,
    imported_at TEXT NOT NULL,
    parser_name TEXT,
    parser_version TEXT,
    parse_status TEXT NOT NULL,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS process_task (
    task_id TEXT PRIMARY KEY,
    component_type TEXT,
    material TEXT,
    material_grade TEXT,
    geometry_json TEXT,
    target_json TEXT,
    priority_mode TEXT,
    created_by TEXT,
    created_at TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS process_recipe (
    recipe_id TEXT PRIMARY KEY,
    task_id TEXT,
    artifact_id TEXT,
    process_type TEXT,
    laser_wavelength_nm REAL,
    pulse_width_fs REAL,
    laser_power_W REAL,
    frequency_kHz REAL,
    scan_speed_mm_s REAL,
    passes INTEGER,
    hatch_spacing_um REAL,
    layer_step_um REAL,
    focus_offset_um REAL,
    fill_pattern TEXT,
    path_strategy TEXT,
    parameters_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS process_run (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    recipe_id TEXT,
    artifact_id TEXT,
    machine_id TEXT,
    operator_id TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_s REAL,
    run_status TEXT,
    alarm_count INTEGER,
    abnormal_flag INTEGER,
    abnormal_summary TEXT
);
CREATE TABLE IF NOT EXISTS measurement_record (
    measurement_id TEXT PRIMARY KEY,
    run_id TEXT,
    artifact_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    raw_value TEXT,
    raw_unit TEXT,
    measurement_method TEXT,
    instrument_id TEXT,
    region_of_interest TEXT,
    measured_at TEXT,
    valid_flag INTEGER
);
CREATE TABLE IF NOT EXISTS experience_candidate (
    candidate_id TEXT PRIMARY KEY,
    task_id TEXT,
    run_id TEXT,
    source_artifact_ids TEXT,
    extracted_claim TEXT NOT NULL,
    evidence_json TEXT,
    confidence REAL,
    status TEXT NOT NULL,
    extracted_by TEXT,
    extracted_at TEXT,
    review_comment TEXT
);
CREATE TABLE IF NOT EXISTS validated_rule (
    rule_id TEXT PRIMARY KEY,
    material TEXT,
    process_type TEXT,
    condition_json TEXT,
    rule_text TEXT NOT NULL,
    recommended_action_json TEXT,
    supporting_case_ids TEXT,
    counter_case_ids TEXT,
    confidence REAL,
    status TEXT,
    version INTEGER,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS bo_training_sample (
    sample_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    material TEXT,
    process_type TEXT,
    x_parameters_json TEXT NOT NULL,
    y_metrics_json TEXT NOT NULL,
    constraints_json TEXT,
    valid_for_training INTEGER NOT NULL,
    invalid_reason TEXT,
    added_at TEXT
);
"""


def init_database(db_path: str | Path | None = None) -> Path:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        rows = conn.execute("PRAGMA database_list").fetchall()
    return Path(rows[0][2]).resolve() if rows else Path(db_path or "")
