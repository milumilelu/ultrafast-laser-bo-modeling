from __future__ import annotations

import pytest

from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.equipment.bounds import apply_task_level_override, require_machine_bounds_for_bo, validate_candidate_within_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def test_bo_tool_reports_missing_action_context_without_active_profile(isolated_root):
    init_database()

    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "recommend_parameters_bo",
        {},
        {"task_spec": {"material": "diamond", "process_type": "ablation"}},
    )

    assert execution.status == "insufficient_data"
    assert "task_spec.objective" in execution.output["missing"]
    assert "equipment_snapshot.machine_bounds" in execution.output["missing"]


def test_bo_reads_active_machine_bounds(isolated_root):
    init_database()
    create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Lab fs laser 1030nm",
            laser_source={
                "pulse_width_min_fs": 500,
                "pulse_width_max_fs": 8000,
                "average_power_min_W": 0.1,
                "average_power_max_W": 20,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 1000,
            },
            optical_setup={"spot_diameter_um": 20},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
            set_active=True,
        )
    )

    result = require_machine_bounds_for_bo()

    assert result["active"] is True
    assert result["machine_bounds"]["laser_power_W"] == [0.1, 20]


def test_bo_candidate_and_override_respect_physical_bounds(isolated_root):
    machine_bounds = {"laser_power_W": [0.1, 20], "frequency_kHz": [50, 1000]}

    invalid = validate_candidate_within_bounds({"laser_power_W": 25}, machine_bounds)
    valid_override = apply_task_level_override(machine_bounds, {"laser_power_W": [0.1, 10]}, "low power objective")

    assert invalid["valid"] is False
    assert invalid["invalid_reason"] == "blocked_by_machine_bounds"
    assert valid_override["machine_bounds"]["laser_power_W"] == [0.1, 10]
    with pytest.raises(ValueError):
        apply_task_level_override(machine_bounds, {"laser_power_W": [0.1, 30]}, "too high")
