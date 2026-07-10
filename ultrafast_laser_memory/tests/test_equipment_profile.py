from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate, EquipmentProfileUpdate
from ultrafast_memory.equipment.service import create_equipment_profile, get_active_equipment_profile, update_equipment_profile


def _profile_payload(set_active: bool = True) -> EquipmentProfileCreate:
    return EquipmentProfileCreate(
        profile_name="Lab fs laser 1030nm",
        machine_id="laser_A",
        laser_source={
            "wavelength_nm": 1030,
            "pulse_width_fixed_fs": 300,
            "average_power_min_W": 0.1,
            "average_power_max_W": 20,
            "frequency_min_kHz": 50,
            "frequency_max_kHz": 1000,
        },
        optical_setup={"spot_diameter_um": 20, "focus_offset_min_um": -100, "focus_offset_max_um": 100},
        motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
        process_capability={
            "passes_min": 1,
            "passes_max": 20,
            "hatch_spacing_min_um": 1,
            "hatch_spacing_max_um": 50,
            "layer_step_min_um": 0.5,
            "layer_step_max_um": 20,
        },
        set_active=set_active,
    )


def test_create_active_profile_and_revision(isolated_root):
    init_database()

    created = create_equipment_profile(_profile_payload())
    active = get_active_equipment_profile()

    assert created["equipment_profile_id"]
    assert created["revision_id"]
    assert active["equipment_profile_id"] == created["equipment_profile_id"]
    assert active["revision_id"] == created["revision_id"]


def test_update_profile_creates_new_revision(isolated_root):
    init_database()
    created = create_equipment_profile(_profile_payload())

    updated = update_equipment_profile(
        created["equipment_profile_id"],
        EquipmentProfileUpdate(optical_setup={"spot_diameter_um": 18, "focus_offset_min_um": -50, "focus_offset_max_um": 80}),
    )

    assert updated["revision_id"] != created["revision_id"]
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM equipment_config_revision WHERE equipment_profile_id = ?",
            (created["equipment_profile_id"],),
        ).fetchone()[0]
    assert count == 2


def test_patch_merges_equipment_section_without_dropping_existing_fields(isolated_root):
    init_database()
    created = create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Simple fs laser",
            laser_source={
                "wavelength_nm": 1030,
                "pulse_width_min_fs": 500,
                "pulse_width_max_fs": 8000,
                "rated_max_power_W": 25,
                "actual_max_power_W": 18,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 1000,
            },
            optical_setup={"spot_diameter_um": 20},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
            set_active=True,
        )
    )

    update_equipment_profile(
        created["equipment_profile_id"],
        EquipmentProfileUpdate(laser_source={"actual_max_power_W": 12}),
    )
    active = get_active_equipment_profile()

    assert active["laser_source"]["wavelength_nm"] == 1030
    assert active["laser_source"]["rated_max_power_W"] == 25
    assert active["laser_source"]["actual_max_power_W"] == 12
    assert active["laser_source"]["frequency_max_kHz"] == 1000


def test_get_active_profile_empty_state(isolated_root):
    init_database()

    assert get_active_equipment_profile() is None
