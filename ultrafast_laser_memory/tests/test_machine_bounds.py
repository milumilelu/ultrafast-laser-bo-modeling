from __future__ import annotations

import pytest

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def test_build_machine_bounds_maps_fixed_and_range_fields(isolated_root):
    init_database()
    create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Lab fs laser 1030nm",
            laser_source={
                "wavelength_nm": 1030,
                "pulse_width_min_fs": 500,
                "pulse_width_max_fs": 8000,
                "average_power_min_W": 0.1,
                "average_power_max_W": 20,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 1000,
            },
            optical_setup={"spot_diameter_um": 20, "focus_offset_min_um": -100, "focus_offset_max_um": 100},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
            process_capability={"passes_min": 1, "passes_max": 20},
            set_active=True,
        )
    )

    result = build_machine_bounds()

    assert result["active"] is True
    assert result["machine_bounds"]["wavelength_nm"] == [1030, 1030]
    assert result["machine_bounds"]["pulse_width_fs"] == [500, 8000]
    assert result["machine_bounds"]["laser_power_W"] == [0.1, 20]
    assert result["machine_bounds"]["frequency_kHz"] == [50, 1000]
    assert result["machine_bounds"]["scan_speed_mm_s"] == [10, 3000]
    assert "hatch_spacing_um" not in result["machine_bounds"]


def test_build_machine_bounds_uses_actual_max_power_field(isolated_root):
    init_database()
    create_equipment_profile(
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

    result = build_machine_bounds()

    assert result["machine_bounds"]["laser_power_W"] == [0, 18]


def test_invalid_negative_and_min_greater_than_max_rejected(isolated_root):
    init_database()

    with pytest.raises(ValueError):
        create_equipment_profile(
            EquipmentProfileCreate(
                profile_name="bad negative",
                laser_source={"average_power_min_W": -1, "average_power_max_W": 20, "frequency_min_kHz": 50, "frequency_max_kHz": 1000},
                motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
                set_active=True,
            )
        )

    with pytest.raises(ValueError):
        create_equipment_profile(
            EquipmentProfileCreate(
                profile_name="bad range",
                laser_source={"average_power_min_W": 20, "average_power_max_W": 1, "frequency_min_kHz": 50, "frequency_max_kHz": 1000},
                motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
                set_active=True,
            )
        )
