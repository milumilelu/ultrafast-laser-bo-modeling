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
