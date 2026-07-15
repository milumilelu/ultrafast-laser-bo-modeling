from fastapi.testclient import TestClient

from ultrafast_memory.agent_runtime.main_agent_loop import run_main_agent_turn
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def test_t300_end_to_end_minimal(isolated_root):
    init_database()
    create_equipment_profile(EquipmentProfileCreate(
        profile_name="V3.1 test femtosecond laser",
        laser_source={
            "wavelength_nm": 1030,
            "pulse_width_min_fs": 500,
            "pulse_width_max_fs": 8000,
            "average_power_min_W": 0.1,
            "average_power_max_W": 5.33,
            "frequency_min_kHz": 2,
            "frequency_max_kHz": 200,
        },
        optical_setup={"spot_diameter_um": 5},
        motion_system={"scan_speed_min_mm_s": 1, "scan_speed_max_mm_s": 200},
        set_active=True,
    ))
    session_id = TestClient(app).post("/chat/sessions", json={}).json()["session_id"]
    result = run_main_agent_turn(
        session_id=session_id,
        message="我想加工 3 mm 厚的 T300 碳纤维板，开一个 4 mm 通孔。",
        message_id="t300-minimal",
        client=None,
    )

    assert result["task_spec"]["material"]["grade"] == "T300"
    assert result["task_spec"]["geometry"]["dimensions"]["diameter_mm"] == 4
    assert [item["tool_name"] for item in result["tool_calls"]] == [
        "get_equipment_context", "recommend_process_parameters",
    ]
    recommendation = result["tool_calls"][1]["result"]["data"]
    assert recommendation["internal_trace"][0]["step"] == "bo_parameter_recommendation"
    assert recommendation["data_support"]["fidelity"] == "not_reported"
    assert "uncertainty" in recommendation
    assert recommendation["allowed_for_trial"] is True
    assert recommendation["allowed_for_formal_process"] is False
    assert result["final_action"]["action"] == "respond"
    assert "NextAction：选择简化试切或完整试切" in result["content"]
    assert result["workflow_state"]["runtime_metrics"]["model_call_count"] == 0
