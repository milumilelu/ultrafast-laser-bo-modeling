from __future__ import annotations

import json

from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def test_chat_projects_active_equipment_only_after_real_tool_call(isolated_root, monkeypatch):
    init_database()
    created = create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Lab fs laser 1030nm",
            laser_source={
                "wavelength_nm": 1030,
                "pulse_width_fixed_fs": 300,
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

    class EquipmentAgent:
        provider = "test"
        model = "equipment-agent"

        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            action = (
                {"action": "call_tool", "decision_summary": "读取当前设备", "tool_name": "get_equipment_context", "arguments": {}}
                if self.calls == 1 else
                {"action": "final_answer", "decision_summary": "设备已读取", "message": "已读取当前设备。"}
            )
            return {"content": json.dumps(action, ensure_ascii=False)}

    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: EquipmentAgent())
    response = handle_chat(ChatRequest(message="读取当前设备配置"))

    assert response.workflow_state["equipment_profile_used"]["equipment_profile_id"] == created["equipment_profile_id"]
    assert response.workflow_state["fixed_equipment_conditions"]["wavelength_nm"] == 1030
    assert response.workflow_state["tunable_equipment_capabilities"]["laser_power_W"]["max"] == 20
    assert any(item["event_type"] == "tool_completed" for item in response.execution_trace)


def test_equipment_tool_context_reports_incomplete_profile(isolated_root):
    init_database()
    created = create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Lab fs laser incomplete optics",
            laser_source={
                "pulse_width_min_fs": 500,
                "pulse_width_max_fs": 8000,
                "average_power_min_W": 0.1,
                "average_power_max_W": 20,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 1000,
            },
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
            set_active=False,
        )
    )
    with get_connection() as conn:
        conn.execute(
            "UPDATE equipment_profile SET is_active = 1, status = 'active' WHERE equipment_profile_id = ?",
            (created["equipment_profile_id"],),
        )
        conn.commit()

    equipment = build_machine_bounds()

    assert equipment["active"] is True
    assert equipment["missing_equipment_fields"] == ["spot_diameter_um"]
