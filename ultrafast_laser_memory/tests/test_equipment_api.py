from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.init_db import init_database


def _payload(set_active: bool = True) -> dict:
    return {
        "profile_name": "Lab fs laser 1030nm",
        "machine_id": "laser_A",
        "laser_source": {
            "wavelength_nm": 1030,
            "pulse_width_fixed_fs": 300,
            "average_power_min_W": 0.1,
            "average_power_max_W": 20,
            "frequency_min_kHz": 50,
            "frequency_max_kHz": 1000,
        },
        "optical_setup": {"spot_diameter_um": 20, "focus_offset_min_um": -100, "focus_offset_max_um": 100},
        "motion_system": {"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 3000},
        "process_capability": {"passes_min": 1, "passes_max": 20, "hatch_spacing_min_um": 1, "hatch_spacing_max_um": 50},
        "set_active": set_active,
    }


def test_equipment_api_profile_active_bounds_activate_patch(isolated_root):
    init_database()
    client = TestClient(app)

    created = client.post("/equipment/profiles", json=_payload(True))
    assert created.status_code == 200
    equipment_profile_id = created.json()["equipment_profile_id"]
    assert created.json()["is_active"] is True

    active = client.get("/equipment/active")
    assert active.status_code == 200
    assert active.json()["equipment_profile_id"] == equipment_profile_id

    bounds = client.get("/equipment/active/machine-bounds")
    assert bounds.status_code == 200
    assert bounds.json()["machine_bounds"]["pulse_width_fs"] == [300, 300]

    updated = client.patch(
        f"/equipment/profiles/{equipment_profile_id}",
        json={"optical_setup": {"spot_diameter_um": 18, "focus_offset_min_um": -80, "focus_offset_max_um": 80}},
    )
    assert updated.status_code == 200
    assert updated.json()["revision_id"] != created.json()["revision_id"]

    activated = client.post(f"/equipment/profiles/{equipment_profile_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


def test_equipment_schema_reports_current_setup_fields(isolated_root):
    init_database()
    client = TestClient(app)

    response = client.get("/equipment/schema")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] >= 2
    assert "actual_max_power_W" in data["required_setup_fields"]
    assert "pulse_width_min_fs" in data["required_setup_fields"]
