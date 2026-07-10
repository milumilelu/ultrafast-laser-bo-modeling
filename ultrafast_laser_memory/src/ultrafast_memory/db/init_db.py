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
CREATE TABLE IF NOT EXISTS chat_session (
    session_id TEXT PRIMARY KEY,
    title TEXT,
    mode TEXT,
    created_at TEXT,
    updated_at TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS chat_message (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT,
    metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS chat_skill_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    selected_skill TEXT,
    confidence REAL,
    reason TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS chat_tool_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    tool_name TEXT,
    input_json TEXT,
    output_json TEXT,
    status TEXT,
    created_at TEXT,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS chat_session_state (
    state_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    active_workflow TEXT,
    active_skill TEXT,
    workflow_stage TEXT,
    collected_slots_json TEXT,
    pending_questions_json TEXT,
    allowed_next_skills_json TEXT,
    debug_router INTEGER DEFAULT 0,
    streaming_enabled INTEGER DEFAULT 0,
    evidence_gap_json TEXT,
    active_knowledge_bootstrap_json TEXT,
    pending_review_task_ids_json TEXT,
    pending_bootstrap_permission INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS chat_route_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    route_source TEXT,
    route_plan_json TEXT,
    confidence REAL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS external_source_artifact (
    source_id TEXT PRIMARY KEY,
    source_type TEXT,
    title TEXT,
    url TEXT,
    doi TEXT,
    authors TEXT,
    published_at TEXT,
    accessed_at TEXT,
    provider TEXT,
    raw_snippet TEXT,
    local_snapshot_path TEXT,
    content_hash TEXT,
    credibility_score REAL,
    status TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_candidate (
    candidate_id TEXT PRIMARY KEY,
    source_id TEXT,
    claim TEXT NOT NULL,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    parameter_json TEXT,
    condition_json TEXT,
    usable_for_json TEXT,
    not_usable_for_json TEXT,
    evidence_type TEXT,
    confidence REAL,
    status TEXT,
    review_status TEXT,
    risk_level TEXT,
    suggested_action TEXT,
    conflict_flag INTEGER,
    duplicate_of TEXT,
    source_quality_score REAL,
    created_at TEXT,
    reviewed_by TEXT,
    review_comment TEXT
);
CREATE TABLE IF NOT EXISTS literature_evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT,
    candidate_id TEXT,
    claim TEXT NOT NULL,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    metric_name TEXT,
    parameter_range_json TEXT,
    condition_json TEXT,
    page_or_section TEXT,
    confidence REAL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS process_prior (
    prior_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    material TEXT,
    process_type TEXT,
    component_type TEXT,
    parameter_name TEXT,
    lower_bound REAL,
    upper_bound REAL,
    unit TEXT,
    condition_json TEXT,
    source_ids_json TEXT,
    confidence REAL,
    status TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS rag_document (
    rag_doc_id TEXT PRIMARY KEY,
    source_id TEXT,
    candidate_id TEXT,
    title TEXT,
    content TEXT NOT NULL,
    metadata_json TEXT,
    indexed INTEGER,
    index_name TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS rag_index_job (
    job_id TEXT PRIMARY KEY,
    rag_doc_id TEXT,
    index_name TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_review_task (
    review_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    review_status TEXT NOT NULL,
    priority TEXT,
    risk_level TEXT,
    assigned_to TEXT,
    created_at TEXT,
    updated_at TEXT,
    due_at TEXT,
    auto_suggestion TEXT,
    review_comment TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_review_action (
    action_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_level TEXT,
    comment TEXT,
    created_at TEXT,
    payload_json TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_conflict (
    conflict_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    existing_knowledge_id TEXT,
    conflict_type TEXT,
    conflict_summary TEXT,
    status TEXT,
    created_at TEXT,
    resolved_at TEXT,
    resolution_comment TEXT
);
CREATE TABLE IF NOT EXISTS workflow_progress (
    progress_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    workflow_id TEXT,
    workflow_type TEXT,
    current_stage TEXT,
    progress_percent REAL,
    status TEXT,
    message TEXT,
    completed_steps_json TEXT,
    pending_steps_json TEXT,
    missing_slots_json TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS reasoning_status_trace (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    workflow_id TEXT,
    event_type TEXT,
    title TEXT,
    summary TEXT,
    detail_json TEXT,
    visibility TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_trace_event (
    event_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_id TEXT,
    event_type TEXT,
    stage TEXT,
    title TEXT,
    summary TEXT,
    progress INTEGER,
    skill TEXT,
    tool TEXT,
    input_summary TEXT,
    output_summary TEXT,
    status TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS equipment_profile (
    equipment_profile_id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL,
    machine_id TEXT,
    manufacturer TEXT,
    model TEXT,
    location TEXT,
    status TEXT,
    is_active INTEGER,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT,
    calibration_date TEXT,
    valid_until TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS laser_source_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    laser_name TEXT,
    wavelength_nm REAL,
    pulse_width_min_fs REAL,
    pulse_width_max_fs REAL,
    pulse_width_fixed_fs REAL,
    average_power_min_W REAL,
    average_power_max_W REAL,
    rated_max_power_W REAL,
    actual_max_power_W REAL,
    frequency_min_kHz REAL,
    frequency_max_kHz REAL,
    pulse_energy_max_uJ REAL,
    beam_quality_M2 REAL,
    polarization TEXT,
    parameters_json TEXT
);
CREATE TABLE IF NOT EXISTS optical_setup_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    objective_name TEXT,
    objective_NA REAL,
    focal_length_mm REAL,
    spot_diameter_um REAL,
    working_distance_mm REAL,
    beam_expander TEXT,
    focus_control_mode TEXT,
    focus_offset_min_um REAL,
    focus_offset_max_um REAL,
    parameters_json TEXT
);
CREATE TABLE IF NOT EXISTS motion_system_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    scan_system_type TEXT,
    galvo_max_speed_mm_s REAL,
    stage_max_speed_mm_s REAL,
    scan_speed_min_mm_s REAL,
    scan_speed_max_mm_s REAL,
    positioning_accuracy_um REAL,
    repeatability_um REAL,
    work_area_x_mm REAL,
    work_area_y_mm REAL,
    work_area_z_mm REAL,
    parameters_json TEXT
);
CREATE TABLE IF NOT EXISTS process_capability_config (
    config_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    passes_min INTEGER,
    passes_max INTEGER,
    hatch_spacing_min_um REAL,
    hatch_spacing_max_um REAL,
    layer_step_min_um REAL,
    layer_step_max_um REAL,
    fill_patterns_supported_json TEXT,
    path_strategies_supported_json TEXT,
    materials_supported_json TEXT,
    process_types_supported_json TEXT,
    parameters_json TEXT
);
CREATE TABLE IF NOT EXISTS equipment_config_revision (
    revision_id TEXT PRIMARY KEY,
    equipment_profile_id TEXT NOT NULL,
    revision_number INTEGER,
    changed_by TEXT,
    changed_at TEXT,
    change_summary TEXT,
    snapshot_json TEXT
);
CREATE TABLE IF NOT EXISTS literature_artifact (
    artifact_id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    archived_path TEXT,
    asset_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size_bytes INTEGER,
    parent_root TEXT,
    parse_status TEXT,
    parser_name TEXT,
    parser_version TEXT,
    error_message TEXT,
    discovered_at TEXT,
    imported_at TEXT,
    UNIQUE(sha256, asset_type)
);
CREATE TABLE IF NOT EXISTS literature_paper (
    paper_id TEXT PRIMARY KEY,
    canonical_title TEXT,
    normalized_title TEXT,
    authors TEXT,
    year TEXT,
    doi TEXT,
    source TEXT,
    url TEXT,
    scenario_id TEXT,
    material TEXT,
    material_grade TEXT,
    component_type TEXT,
    process_type TEXT,
    laser_type TEXT,
    wavelength_nm REAL,
    pulse_width_fs REAL,
    power_or_energy TEXT,
    frequency_kHz REAL,
    scan_speed_mm_s REAL,
    beam_shape TEXT,
    environment TEXT,
    geometry_json TEXT,
    quality_metrics_json TEXT,
    defects_json TEXT,
    measurement_methods_json TEXT,
    usable_for_json TEXT,
    not_usable_for_json TEXT,
    evidence_level TEXT,
    review_status TEXT,
    canonical_artifact_id TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_literature_paper_doi
ON literature_paper(doi) WHERE doi IS NOT NULL AND doi != '';
CREATE INDEX IF NOT EXISTS idx_literature_paper_title_year
ON literature_paper(normalized_title, year);
CREATE TABLE IF NOT EXISTS literature_paper_source (
    link_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    source_role TEXT,
    version_label TEXT,
    is_canonical INTEGER,
    created_at TEXT,
    UNIQUE(paper_id, artifact_id)
);
CREATE TABLE IF NOT EXISTS literature_section (
    section_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    artifact_id TEXT,
    section_type TEXT,
    section_title TEXT,
    page_start INTEGER,
    page_end INTEGER,
    text TEXT,
    text_hash TEXT,
    parser_version TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS literature_chunk (
    chunk_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    section_id TEXT,
    artifact_id TEXT,
    chunk_index INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    section_type TEXT,
    section_title TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_estimate INTEGER,
    metadata_json TEXT,
    evidence_level TEXT,
    review_status TEXT,
    active INTEGER,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(paper_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_literature_chunk_filter
ON literature_chunk(active, review_status, section_type);
CREATE TABLE IF NOT EXISTS rag_index (
    index_id TEXT PRIMARY KEY,
    index_name TEXT NOT NULL,
    index_type TEXT NOT NULL,
    embedding_provider TEXT,
    embedding_model TEXT,
    embedding_dimension INTEGER,
    distance_metric TEXT,
    config_json TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS rag_index_entry (
    entry_id TEXT PRIMARY KEY,
    index_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    vector_ref TEXT,
    lexical_ref TEXT,
    content_hash TEXT,
    indexed_at TEXT,
    status TEXT,
    error_message TEXT,
    UNIQUE(index_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS rag_ingestion_job (
    job_id TEXT PRIMARY KEY,
    root_path TEXT,
    mode TEXT,
    status TEXT,
    discovered_count INTEGER,
    ingested_count INTEGER,
    skipped_count INTEGER,
    failed_count INTEGER,
    needs_review_count INTEGER,
    started_at TEXT,
    finished_at TEXT,
    error_summary TEXT,
    config_json TEXT
);
CREATE TABLE IF NOT EXISTS rag_query_trace (
    query_id TEXT PRIMARY KEY,
    session_id TEXT,
    user_query TEXT,
    normalized_query TEXT,
    filters_json TEXT,
    lexical_hits_json TEXT,
    vector_hits_json TEXT,
    reranked_hits_json TEXT,
    evidence_pack_json TEXT,
    created_at TEXT
);
"""


CHAT_SESSION_STATE_COLUMNS = {
    "evidence_gap_json": "TEXT",
    "active_knowledge_bootstrap_json": "TEXT",
    "pending_review_task_ids_json": "TEXT",
    "pending_bootstrap_permission": "INTEGER DEFAULT 0",
}

TABLE_COLUMNS = {
    "laser_source_config": {
        "rated_max_power_W": "REAL",
        "actual_max_power_W": "REAL",
    },
    "knowledge_candidate": {
        "paper_id": "TEXT",
        "evidence_level": "TEXT",
        "extraction_method": "TEXT",
    },
}


def init_database(db_path: str | Path | None = None) -> Path:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(chat_session_state)").fetchall()}
        for column, column_type in CHAT_SESSION_STATE_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE chat_session_state ADD COLUMN {column} {column_type}")
        for table, columns in TABLE_COLUMNS.items():
            existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for column, column_type in columns.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()
        rows = conn.execute("PRAGMA database_list").fetchall()
    return Path(rows[0][2]).resolve() if rows else Path(db_path or "")
