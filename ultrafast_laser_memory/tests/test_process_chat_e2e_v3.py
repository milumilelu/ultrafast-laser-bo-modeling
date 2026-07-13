from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.app.api import app
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


def test_streaming_process_chat_accumulates_fields_and_requires_trial_choice(isolated_root):
    _equipment()
    client = TestClient(app)
    session_id = client.post("/chat/sessions", json={}).json()["session_id"]

    _, first = _stream(client, session_id, "我想切割5mm厚的碳纤维板，板号T300")
    assert "REQUIREMENTS_PENDING" in first
    assert "推荐参数" not in first
    _, second = _stream(client, session_id, "1、切缝碳纤维无分层；2、无；3、可多次分层加工")
    assert "REQUIREMENTS_PENDING" in second
    events, third = _stream(client, session_id, "10cm直线；无效率要求；压缩空气")
    assert "TRIAL_MODE_PENDING" in third
    assert "[简化试切] [完整试切] [跳过试切]" in third
    assert any(item.get("event_type") == "tool_started" for item in events)
    _, fourth = _stream(client, session_id, "选择简化试切")
    assert "BO 与 RAG 均不足" in fourth
    assert "允许探索性候选" in fourth
