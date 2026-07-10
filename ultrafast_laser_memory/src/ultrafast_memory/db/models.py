from __future__ import annotations

from sqlalchemy import Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ultrafast_memory.db.base import Base


class RawArtifact(Base):
    __tablename__ = "raw_artifact"
    artifact_id: Mapped[str] = mapped_column(Text, primary_key=True)
    file_path: Mapped[str] = mapped_column(Text)
    archived_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text, unique=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text)
    modified_at: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[str] = mapped_column(Text)
    parser_name: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ProcessTask(Base):
    __tablename__ = "process_task"
    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    component_type: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    material_grade: Mapped[str | None] = mapped_column(Text)
    geometry_json: Mapped[str | None] = mapped_column(Text)
    target_json: Mapped[str | None] = mapped_column(Text)
    priority_mode: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)


class ProcessRecipe(Base):
    __tablename__ = "process_recipe"
    recipe_id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(Text)
    process_type: Mapped[str | None] = mapped_column(Text)
    laser_wavelength_nm: Mapped[float | None] = mapped_column(Float)
    pulse_width_fs: Mapped[float | None] = mapped_column(Float)
    laser_power_W: Mapped[float | None] = mapped_column(Float)
    frequency_kHz: Mapped[float | None] = mapped_column(Float)
    scan_speed_mm_s: Mapped[float | None] = mapped_column(Float)
    passes: Mapped[int | None] = mapped_column(Integer)
    hatch_spacing_um: Mapped[float | None] = mapped_column(Float)
    layer_step_um: Mapped[float | None] = mapped_column(Float)
    focus_offset_um: Mapped[float | None] = mapped_column(Float)
    fill_pattern: Mapped[str | None] = mapped_column(Text)
    path_strategy: Mapped[str | None] = mapped_column(Text)
    parameters_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class ProcessRun(Base):
    __tablename__ = "process_run"
    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text)
    recipe_id: Mapped[str | None] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(Text)
    machine_id: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[str | None] = mapped_column(Text)
    end_time: Mapped[str | None] = mapped_column(Text)
    duration_s: Mapped[float | None] = mapped_column(Float)
    run_status: Mapped[str | None] = mapped_column(Text)
    alarm_count: Mapped[int | None] = mapped_column(Integer)
    abnormal_flag: Mapped[int | None] = mapped_column(Integer)
    abnormal_summary: Mapped[str | None] = mapped_column(Text)


class ChatSession(Base):
    __tablename__ = "chat_session"
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)


class ChatSkillTrace(Base):
    __tablename__ = "chat_skill_trace"
    trace_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    selected_skill: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class ChatToolTrace(Base):
    __tablename__ = "chat_tool_trace"
    trace_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(Text)
    input_json: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ChatSessionState(Base):
    __tablename__ = "chat_session_state"
    state_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, unique=True)
    active_workflow: Mapped[str | None] = mapped_column(Text)
    active_skill: Mapped[str | None] = mapped_column(Text)
    workflow_stage: Mapped[str | None] = mapped_column(Text)
    collected_slots_json: Mapped[str | None] = mapped_column(Text)
    pending_questions_json: Mapped[str | None] = mapped_column(Text)
    allowed_next_skills_json: Mapped[str | None] = mapped_column(Text)
    debug_router: Mapped[int | None] = mapped_column(Integer)
    streaming_enabled: Mapped[int | None] = mapped_column(Integer)
    evidence_gap_json: Mapped[str | None] = mapped_column(Text)
    active_knowledge_bootstrap_json: Mapped[str | None] = mapped_column(Text)
    pending_review_task_ids_json: Mapped[str | None] = mapped_column(Text)
    pending_bootstrap_permission: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[str | None] = mapped_column(Text)


class ChatRouteTrace(Base):
    __tablename__ = "chat_route_trace"
    trace_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    route_source: Mapped[str | None] = mapped_column(Text)
    route_plan_json: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(Text)


class ExternalSourceArtifact(Base):
    __tablename__ = "external_source_artifact"
    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_type: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text)
    accessed_at: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    raw_snippet: Mapped[str | None] = mapped_column(Text)
    local_snapshot_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    credibility_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(Text)


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidate"
    candidate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(Text)
    claim: Mapped[str] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    process_type: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(Text)
    parameter_json: Mapped[str | None] = mapped_column(Text)
    condition_json: Mapped[str | None] = mapped_column(Text)
    usable_for_json: Mapped[str | None] = mapped_column(Text)
    not_usable_for_json: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    conflict_flag: Mapped[int | None] = mapped_column(Integer)
    duplicate_of: Mapped[str | None] = mapped_column(Text)
    source_quality_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    review_comment: Mapped[str | None] = mapped_column(Text)
    paper_id: Mapped[str | None] = mapped_column(Text)
    evidence_level: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(Text)


class LiteratureEvidence(Base):
    __tablename__ = "literature_evidence"
    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(Text)
    candidate_id: Mapped[str | None] = mapped_column(Text)
    claim: Mapped[str] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    process_type: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(Text)
    metric_name: Mapped[str | None] = mapped_column(Text)
    parameter_range_json: Mapped[str | None] = mapped_column(Text)
    condition_json: Mapped[str | None] = mapped_column(Text)
    page_or_section: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(Text)


class ProcessPrior(Base):
    __tablename__ = "process_prior"
    prior_id: Mapped[str] = mapped_column(Text, primary_key=True)
    candidate_id: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    process_type: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(Text)
    parameter_name: Mapped[str | None] = mapped_column(Text)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(Text)
    condition_json: Mapped[str | None] = mapped_column(Text)
    source_ids_json: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class RagDocument(Base):
    __tablename__ = "rag_document"
    rag_doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(Text)
    candidate_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    indexed: Mapped[int | None] = mapped_column(Integer)
    index_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class RagIndexJob(Base):
    __tablename__ = "rag_index_job"
    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    rag_doc_id: Mapped[str | None] = mapped_column(Text)
    index_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class KnowledgeReviewTask(Base):
    __tablename__ = "knowledge_review_task"
    review_id: Mapped[str] = mapped_column(Text, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[str | None] = mapped_column(Text)
    auto_suggestion: Mapped[str | None] = mapped_column(Text)
    review_comment: Mapped[str | None] = mapped_column(Text)


class KnowledgeReviewAction(Base):
    __tablename__ = "knowledge_review_action"
    action_id: Mapped[str] = mapped_column(Text, primary_key=True)
    review_id: Mapped[str] = mapped_column(Text)
    candidate_id: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target_level: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text)


class KnowledgeConflict(Base):
    __tablename__ = "knowledge_conflict"
    conflict_id: Mapped[str] = mapped_column(Text, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(Text)
    existing_knowledge_id: Mapped[str | None] = mapped_column(Text)
    conflict_type: Mapped[str | None] = mapped_column(Text)
    conflict_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    resolution_comment: Mapped[str | None] = mapped_column(Text)


class WorkflowProgress(Base):
    __tablename__ = "workflow_progress"
    progress_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text)
    workflow_id: Mapped[str | None] = mapped_column(Text)
    workflow_type: Mapped[str | None] = mapped_column(Text)
    current_stage: Mapped[str | None] = mapped_column(Text)
    progress_percent: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    completed_steps_json: Mapped[str | None] = mapped_column(Text)
    pending_steps_json: Mapped[str | None] = mapped_column(Text)
    missing_slots_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)


class ReasoningStatusTrace(Base):
    __tablename__ = "reasoning_status_trace"
    trace_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    workflow_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    detail_json: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class AgentTraceEvent(Base):
    __tablename__ = "agent_trace_event"
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int | None] = mapped_column(Integer)
    skill: Mapped[str | None] = mapped_column(Text)
    tool: Mapped[str | None] = mapped_column(Text)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class EquipmentProfile(Base):
    __tablename__ = "equipment_profile"
    equipment_profile_id: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_name: Mapped[str] = mapped_column(Text)
    machine_id: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)
    calibration_date: Mapped[str | None] = mapped_column(Text)
    valid_until: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class LaserSourceConfig(Base):
    __tablename__ = "laser_source_config"
    config_id: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_profile_id: Mapped[str] = mapped_column(Text)
    laser_name: Mapped[str | None] = mapped_column(Text)
    wavelength_nm: Mapped[float | None] = mapped_column(Float)
    pulse_width_min_fs: Mapped[float | None] = mapped_column(Float)
    pulse_width_max_fs: Mapped[float | None] = mapped_column(Float)
    pulse_width_fixed_fs: Mapped[float | None] = mapped_column(Float)
    average_power_min_W: Mapped[float | None] = mapped_column(Float)
    average_power_max_W: Mapped[float | None] = mapped_column(Float)
    rated_max_power_W: Mapped[float | None] = mapped_column(Float)
    actual_max_power_W: Mapped[float | None] = mapped_column(Float)
    frequency_min_kHz: Mapped[float | None] = mapped_column(Float)
    frequency_max_kHz: Mapped[float | None] = mapped_column(Float)
    pulse_energy_max_uJ: Mapped[float | None] = mapped_column(Float)
    beam_quality_M2: Mapped[float | None] = mapped_column(Float)
    polarization: Mapped[str | None] = mapped_column(Text)
    parameters_json: Mapped[str | None] = mapped_column(Text)


class OpticalSetupConfig(Base):
    __tablename__ = "optical_setup_config"
    config_id: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_profile_id: Mapped[str] = mapped_column(Text)
    objective_name: Mapped[str | None] = mapped_column(Text)
    objective_NA: Mapped[float | None] = mapped_column(Float)
    focal_length_mm: Mapped[float | None] = mapped_column(Float)
    spot_diameter_um: Mapped[float | None] = mapped_column(Float)
    working_distance_mm: Mapped[float | None] = mapped_column(Float)
    beam_expander: Mapped[str | None] = mapped_column(Text)
    focus_control_mode: Mapped[str | None] = mapped_column(Text)
    focus_offset_min_um: Mapped[float | None] = mapped_column(Float)
    focus_offset_max_um: Mapped[float | None] = mapped_column(Float)
    parameters_json: Mapped[str | None] = mapped_column(Text)


class MotionSystemConfig(Base):
    __tablename__ = "motion_system_config"
    config_id: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_profile_id: Mapped[str] = mapped_column(Text)
    scan_system_type: Mapped[str | None] = mapped_column(Text)
    galvo_max_speed_mm_s: Mapped[float | None] = mapped_column(Float)
    stage_max_speed_mm_s: Mapped[float | None] = mapped_column(Float)
    scan_speed_min_mm_s: Mapped[float | None] = mapped_column(Float)
    scan_speed_max_mm_s: Mapped[float | None] = mapped_column(Float)
    positioning_accuracy_um: Mapped[float | None] = mapped_column(Float)
    repeatability_um: Mapped[float | None] = mapped_column(Float)
    work_area_x_mm: Mapped[float | None] = mapped_column(Float)
    work_area_y_mm: Mapped[float | None] = mapped_column(Float)
    work_area_z_mm: Mapped[float | None] = mapped_column(Float)
    parameters_json: Mapped[str | None] = mapped_column(Text)


class ProcessCapabilityConfig(Base):
    __tablename__ = "process_capability_config"
    config_id: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_profile_id: Mapped[str] = mapped_column(Text)
    passes_min: Mapped[int | None] = mapped_column(Integer)
    passes_max: Mapped[int | None] = mapped_column(Integer)
    hatch_spacing_min_um: Mapped[float | None] = mapped_column(Float)
    hatch_spacing_max_um: Mapped[float | None] = mapped_column(Float)
    layer_step_min_um: Mapped[float | None] = mapped_column(Float)
    layer_step_max_um: Mapped[float | None] = mapped_column(Float)
    fill_patterns_supported_json: Mapped[str | None] = mapped_column(Text)
    path_strategies_supported_json: Mapped[str | None] = mapped_column(Text)
    materials_supported_json: Mapped[str | None] = mapped_column(Text)
    process_types_supported_json: Mapped[str | None] = mapped_column(Text)
    parameters_json: Mapped[str | None] = mapped_column(Text)


class EquipmentConfigRevision(Base):
    __tablename__ = "equipment_config_revision"
    revision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_profile_id: Mapped[str] = mapped_column(Text)
    revision_number: Mapped[int | None] = mapped_column(Integer)
    changed_by: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[str | None] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text)
    snapshot_json: Mapped[str | None] = mapped_column(Text)


class LiteratureArtifact(Base):
    __tablename__ = "literature_artifact"
    artifact_id: Mapped[str] = mapped_column(Text, primary_key=True)
    original_path: Mapped[str] = mapped_column(Text)
    archived_path: Mapped[str | None] = mapped_column(Text)
    asset_type: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    parent_root: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str | None] = mapped_column(Text)
    parser_name: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[str | None] = mapped_column(Text)


class LiteraturePaper(Base):
    __tablename__ = "literature_paper"
    paper_id: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_title: Mapped[str | None] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    year: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    scenario_id: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    material_grade: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(Text)
    process_type: Mapped[str | None] = mapped_column(Text)
    laser_type: Mapped[str | None] = mapped_column(Text)
    wavelength_nm: Mapped[float | None] = mapped_column(Float)
    pulse_width_fs: Mapped[float | None] = mapped_column(Float)
    power_or_energy: Mapped[str | None] = mapped_column(Text)
    frequency_kHz: Mapped[float | None] = mapped_column(Float)
    scan_speed_mm_s: Mapped[float | None] = mapped_column(Float)
    beam_shape: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)
    geometry_json: Mapped[str | None] = mapped_column(Text)
    quality_metrics_json: Mapped[str | None] = mapped_column(Text)
    defects_json: Mapped[str | None] = mapped_column(Text)
    measurement_methods_json: Mapped[str | None] = mapped_column(Text)
    usable_for_json: Mapped[str | None] = mapped_column(Text)
    not_usable_for_json: Mapped[str | None] = mapped_column(Text)
    evidence_level: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(Text)
    canonical_artifact_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)


class LiteraturePaperSource(Base):
    __tablename__ = "literature_paper_source"
    link_id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text)
    artifact_id: Mapped[str] = mapped_column(Text)
    source_role: Mapped[str | None] = mapped_column(Text)
    version_label: Mapped[str | None] = mapped_column(Text)
    is_canonical: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text)


class LiteratureSection(Base):
    __tablename__ = "literature_section"
    section_id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(Text)
    section_type: Mapped[str | None] = mapped_column(Text)
    section_title: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    text_hash: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class LiteratureChunk(Base):
    __tablename__ = "literature_chunk"
    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text)
    section_id: Mapped[str | None] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(Text)
    chunk_index: Mapped[int | None] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_type: Mapped[str | None] = mapped_column(Text)
    section_title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    evidence_level: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(Text)
    active: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)


class RagIndex(Base):
    __tablename__ = "rag_index"
    index_id: Mapped[str] = mapped_column(Text, primary_key=True)
    index_name: Mapped[str] = mapped_column(Text)
    index_type: Mapped[str] = mapped_column(Text)
    embedding_provider: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    distance_metric: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)


class RagIndexEntry(Base):
    __tablename__ = "rag_index_entry"
    entry_id: Mapped[str] = mapped_column(Text, primary_key=True)
    index_id: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[str] = mapped_column(Text)
    vector_ref: Mapped[str | None] = mapped_column(Text)
    lexical_ref: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class RagIngestionJob(Base):
    __tablename__ = "rag_ingestion_job"
    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    root_path: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    discovered_count: Mapped[int | None] = mapped_column(Integer)
    ingested_count: Mapped[int | None] = mapped_column(Integer)
    skipped_count: Mapped[int | None] = mapped_column(Integer)
    failed_count: Mapped[int | None] = mapped_column(Integer)
    needs_review_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[str | None] = mapped_column(Text)


class RagQueryTrace(Base):
    __tablename__ = "rag_query_trace"
    query_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text)
    user_query: Mapped[str | None] = mapped_column(Text)
    normalized_query: Mapped[str | None] = mapped_column(Text)
    filters_json: Mapped[str | None] = mapped_column(Text)
    lexical_hits_json: Mapped[str | None] = mapped_column(Text)
    vector_hits_json: Mapped[str | None] = mapped_column(Text)
    reranked_hits_json: Mapped[str | None] = mapped_column(Text)
    evidence_pack_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
