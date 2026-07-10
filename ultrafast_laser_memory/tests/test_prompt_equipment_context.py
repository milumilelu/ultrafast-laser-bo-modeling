from __future__ import annotations

from ultrafast_memory.chat.prompt_builder import build_system_prompt
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def test_system_prompt_includes_active_equipment_bounds(isolated_root):
    init_database()
    create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Lab fs laser 1030nm",
            laser_source={
                "wavelength_nm": 1030,
                "pulse_width_min_fs": 500,
                "pulse_width_max_fs": 8000,
                "actual_max_power_W": 18,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 1000,
            },
            optical_setup={"spot_diameter_um": 20},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
            set_active=True,
        )
    )

    prompt = build_system_prompt("task_intake")

    assert "当前 active 设备配置已加载" in prompt
    assert "pulse_width_fs" in prompt
    assert "不要再向用户追问已知的波长、脉宽、功率、频率、扫描速度或光斑" in prompt
