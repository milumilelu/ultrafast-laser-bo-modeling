from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate, EquipmentProfileUpdate
from ultrafast_memory.equipment.validation import validate_equipment_payload


SECTION_TABLES = {
    "laser_source": "laser_source_config",
    "optical_setup": "optical_setup_config",
    "motion_system": "motion_system_config",
    "process_capability": "process_capability_config",
}

SECTION_COLUMNS = {
    "laser_source": {
        "laser_name",
        "wavelength_nm",
        "pulse_width_min_fs",
        "pulse_width_max_fs",
        "pulse_width_fixed_fs",
        "average_power_min_W",
        "average_power_max_W",
        "rated_max_power_W",
        "actual_max_power_W",
        "frequency_min_kHz",
        "frequency_max_kHz",
        "pulse_energy_max_uJ",
        "beam_quality_M2",
        "polarization",
    },
    "optical_setup": {
        "objective_name",
        "objective_NA",
        "focal_length_mm",
        "spot_diameter_um",
        "working_distance_mm",
        "beam_expander",
        "focus_control_mode",
        "focus_offset_min_um",
        "focus_offset_max_um",
    },
    "motion_system": {
        "scan_system_type",
        "galvo_max_speed_mm_s",
        "stage_max_speed_mm_s",
        "scan_speed_min_mm_s",
        "scan_speed_max_mm_s",
        "positioning_accuracy_um",
        "repeatability_um",
        "work_area_x_mm",
        "work_area_y_mm",
        "work_area_z_mm",
    },
    "process_capability": {
        "passes_min",
        "passes_max",
        "hatch_spacing_min_um",
        "hatch_spacing_max_um",
        "layer_step_min_um",
        "layer_step_max_um",
        "fill_patterns_supported_json",
        "path_strategies_supported_json",
        "materials_supported_json",
        "process_types_supported_json",
    },
}

LIST_FIELDS = {
    "fill_patterns_supported": "fill_patterns_supported_json",
    "path_strategies_supported": "path_strategies_supported_json",
    "materials_supported": "materials_supported_json",
    "process_types_supported": "process_types_supported_json",
}


def create_equipment_profile(req: EquipmentProfileCreate) -> dict[str, Any]:
    init_database()
    validate_equipment_payload(
        req.laser_source,
        req.optical_setup,
        req.motion_system,
        req.process_capability,
        require_active_minimum=req.set_active,
    )
    now = utc_now_iso()
    equipment_profile_id = stable_id("eq", req.profile_name, req.machine_id or "", now)
    profile = {
        "equipment_profile_id": equipment_profile_id,
        "profile_name": req.profile_name,
        "machine_id": req.machine_id,
        "manufacturer": req.manufacturer,
        "model": req.model,
        "location": req.location,
        "status": "active" if req.set_active else "draft",
        "is_active": int(req.set_active),
        "created_by": req.created_by,
        "created_at": now,
        "updated_at": now,
        "calibration_date": req.calibration_date,
        "valid_until": req.valid_until,
        "notes": req.notes,
    }
    with get_connection() as conn:
        if req.set_active:
            _deactivate_all(conn)
        conn.execute(
            """
            INSERT INTO equipment_profile VALUES (
              :equipment_profile_id, :profile_name, :machine_id, :manufacturer,
              :model, :location, :status, :is_active, :created_by, :created_at,
              :updated_at, :calibration_date, :valid_until, :notes
            )
            """,
            profile,
        )
        _replace_sections(conn, equipment_profile_id, req.model_dump(mode="json"))
        revision_id = _create_revision(conn, equipment_profile_id, req.created_by, "create equipment profile")
        conn.commit()
    return {"equipment_profile_id": equipment_profile_id, "revision_id": revision_id, "is_active": req.set_active}


def list_equipment_profiles() -> list[dict[str, Any]]:
    init_database()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM equipment_profile ORDER BY is_active DESC, updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_active_equipment_profile() -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM equipment_profile WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        return _load_profile(conn, row["equipment_profile_id"])


def get_equipment_profile(equipment_profile_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        profile = _load_profile(conn, equipment_profile_id)
    if not profile:
        raise ValueError(f"equipment profile not found: {equipment_profile_id}")
    return profile


def activate_equipment_profile(equipment_profile_id: str, changed_by: str | None = None) -> dict[str, Any]:
    init_database()
    profile = get_equipment_profile(equipment_profile_id)
    validate_equipment_payload(
        profile.get("laser_source"),
        profile.get("optical_setup"),
        profile.get("motion_system"),
        profile.get("process_capability"),
        require_active_minimum=True,
    )
    now = utc_now_iso()
    with get_connection() as conn:
        _deactivate_all(conn)
        conn.execute(
            "UPDATE equipment_profile SET is_active = 1, status = 'active', updated_at = ? WHERE equipment_profile_id = ?",
            (now, equipment_profile_id),
        )
        revision_id = _create_revision(conn, equipment_profile_id, changed_by, "activate equipment profile")
        conn.commit()
    return {"equipment_profile_id": equipment_profile_id, "revision_id": revision_id, "is_active": True}


def update_equipment_profile(equipment_profile_id: str, req: EquipmentProfileUpdate) -> dict[str, Any]:
    init_database()
    current = get_equipment_profile(equipment_profile_id)
    update = req.model_dump(exclude_unset=True, mode="json")
    sections = {
        "laser_source": update.pop("laser_source", None),
        "optical_setup": update.pop("optical_setup", None),
        "motion_system": update.pop("motion_system", None),
        "process_capability": update.pop("process_capability", None),
    }
    merged_sections = {}
    for name in SECTION_TABLES:
        current_section = dict(current.get(name) or {})
        if sections[name] is not None:
            current_section.update(sections[name] or {})
        merged_sections[name] = current_section
    validate_equipment_payload(
        merged_sections["laser_source"],
        merged_sections["optical_setup"],
        merged_sections["motion_system"],
        merged_sections["process_capability"],
        require_active_minimum=bool(current.get("is_active")),
    )
    changed_by = update.pop("changed_by", None)
    update["updated_at"] = utc_now_iso()
    assignments = [f"{key} = ?" for key in update if key in _profile_columns()]
    params = [update[key] for key in update if key in _profile_columns()]
    with get_connection() as conn:
        if assignments:
            conn.execute(
                f"UPDATE equipment_profile SET {', '.join(assignments)} WHERE equipment_profile_id = ?",
                [*params, equipment_profile_id],
            )
        section_payload = {name: merged_sections[name] for name, value in sections.items() if value is not None}
        if section_payload:
            _replace_sections(conn, equipment_profile_id, section_payload)
        revision_id = _create_revision(conn, equipment_profile_id, changed_by, "update equipment profile")
        conn.commit()
    return {"equipment_profile_id": equipment_profile_id, "revision_id": revision_id, "is_active": bool(current.get("is_active"))}


def latest_revision_id(equipment_profile_id: str) -> str | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT revision_id FROM equipment_config_revision
            WHERE equipment_profile_id = ?
            ORDER BY revision_number DESC, changed_at DESC
            LIMIT 1
            """,
            (equipment_profile_id,),
        ).fetchone()
    return row["revision_id"] if row else None


def _deactivate_all(conn) -> None:
    now = utc_now_iso()
    conn.execute("UPDATE equipment_profile SET is_active = 0, status = 'inactive', updated_at = ? WHERE is_active = 1", (now,))


def _replace_sections(conn, equipment_profile_id: str, payload: dict[str, Any]) -> None:
    for section, table in SECTION_TABLES.items():
        if section not in payload:
            continue
        data = payload.get(section) or {}
        conn.execute(f"DELETE FROM {table} WHERE equipment_profile_id = ?", (equipment_profile_id,))
        normalized = _normalize_section(section, data)
        normalized["config_id"] = stable_id("eqcfg", equipment_profile_id, section)
        normalized["equipment_profile_id"] = equipment_profile_id
        columns = ["config_id", "equipment_profile_id", *sorted(SECTION_COLUMNS[section]), "parameters_json"]
        values = [normalized.get(column) for column in columns]
        placeholders = ", ".join(["?"] * len(columns))
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", values)


def _normalize_section(section: str, data: dict[str, Any]) -> dict[str, Any]:
    allowed = SECTION_COLUMNS[section]
    normalized: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in data.items():
        db_key = LIST_FIELDS.get(key, key)
        if db_key in allowed:
            if db_key.endswith("_json") and not isinstance(value, str):
                normalized[db_key] = json.dumps(value, ensure_ascii=False)
            else:
                normalized[db_key] = value
        else:
            extra[key] = value
    normalized["parameters_json"] = json.dumps(extra, ensure_ascii=False) if extra else None
    return normalized


def _load_profile(conn, equipment_profile_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM equipment_profile WHERE equipment_profile_id = ?", (equipment_profile_id,)).fetchone()
    if not row:
        return None
    profile = dict(row)
    for section, table in SECTION_TABLES.items():
        section_row = conn.execute(f"SELECT * FROM {table} WHERE equipment_profile_id = ?", (equipment_profile_id,)).fetchone()
        profile[section] = _section_dict(dict(section_row)) if section_row else {}
    profile["revision_id"] = latest_revision_id(equipment_profile_id)
    return profile


def _section_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in row.items() if key not in {"config_id", "equipment_profile_id", "parameters_json"} and value is not None}
    for alias, json_key in LIST_FIELDS.items():
        if json_key in result:
            result[alias] = _loads(result.pop(json_key), [])
    result.update(_loads(row.get("parameters_json"), {}))
    return result


def _create_revision(conn, equipment_profile_id: str, changed_by: str | None, change_summary: str) -> str:
    row = conn.execute(
        "SELECT COALESCE(MAX(revision_number), 0) AS n FROM equipment_config_revision WHERE equipment_profile_id = ?",
        (equipment_profile_id,),
    ).fetchone()
    revision_number = int(row["n"] or 0) + 1
    now = utc_now_iso()
    snapshot = _load_profile_snapshot(conn, equipment_profile_id)
    revision_id = stable_id("eqrev", equipment_profile_id, revision_number, now)
    conn.execute(
        "INSERT INTO equipment_config_revision VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            revision_id,
            equipment_profile_id,
            revision_number,
            changed_by,
            now,
            change_summary,
            json.dumps(snapshot, ensure_ascii=False),
        ),
    )
    return revision_id


def _load_profile_snapshot(conn, equipment_profile_id: str) -> dict[str, Any]:
    profile = conn.execute("SELECT * FROM equipment_profile WHERE equipment_profile_id = ?", (equipment_profile_id,)).fetchone()
    snapshot = dict(profile) if profile else {}
    for section, table in SECTION_TABLES.items():
        row = conn.execute(f"SELECT * FROM {table} WHERE equipment_profile_id = ?", (equipment_profile_id,)).fetchone()
        snapshot[section] = _section_dict(dict(row)) if row else {}
    return snapshot


def _profile_columns() -> set[str]:
    return {
        "profile_name",
        "machine_id",
        "manufacturer",
        "model",
        "location",
        "status",
        "created_by",
        "calibration_date",
        "valid_until",
        "notes",
        "updated_at",
    }


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
