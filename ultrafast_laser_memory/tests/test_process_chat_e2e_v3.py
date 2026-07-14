from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def _equipment():
    create_equipment_profile(EquipmentProfileCreate(
        profile_name="V3 test laser", set_active=True,
        laser_source={"pulse_width_min_fs": 500, "pulse_width_max_fs": 8000,
                      "average_power_min_W": 0.1, "average_power_max_W": 5.33,
                      "frequency_min_kHz": 2, "frequency_max_kHz": 200},
        optical_setup={"spot_diameter_um": 5, "focus_control_mode": "automatic_z"},
        motion_system={"scan_speed_min_mm_s": 1, "scan_speed_max_mm_s": 200}))


def _stream(client: TestClient, session_id: str, message: str) -> tuple[list[dict], str]:
    response = client.post("/chat/stream_ndjson", json={"session_id": session_id, "message": message,
                                                        "use_skills": True, "stream": True})
    events = [json.loads(line) for line in response.text.splitlines() if line]
    return events, "".join(item.get("content", "") for item in events if item.get("type") == "delta")


def test_streaming_main_agent_accumulates_progressive_task_fields(isolated_root):
    _equipment()
    client = TestClient(app)
    session_id = client.post("/chat/sessions", json={}).json()["session_id"]

    first_events, first = _stream(
        client, session_id, "加工类型=切割；材料=CFRP_T300；厚度=5mm"
    )
    assert "已保存" in first
    assert "推荐参数" not in first
    assert len([item for item in first_events if item.get("type") == "progress"]) == 1
    assert next(item for item in first_events if item.get("type") == "meta")["model"] == \
        "main-agent-loop-v1"
    state = next(item for item in first_events if item.get("type") == "workflow_state")
    assert state["task_spec"]["process_type"] == "cutting"
    assert state["task_spec"]["material"] == "CFRP_T300"
    assert state["task_spec"]["thickness_mm"] == 5.0
    assert state["next_required_action"]["action_type"] == "continue_workflow"
    _stream(
        client, session_id, "质量要求=切缝碳纤维无分层；允许分层切割=true"
    )
    events, _ = _stream(
        client, session_id,
        "切割长度=10cm；轮廓=直线；效率要求=无；辅助介质=压缩空气",
    )
    final_state = next(item for item in events if item.get("type") == "workflow_state")
    assert final_state["task_spec"]["cut_length_mm"] == 100
    assert final_state["task_spec"]["layer_cut_allowed"] is True
    assert "selected_trial_mode" not in final_state
