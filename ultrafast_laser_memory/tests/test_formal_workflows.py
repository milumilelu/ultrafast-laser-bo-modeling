from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def _equipment():
    create_equipment_profile(
        EquipmentProfileCreate(
            profile_name="Workflow equipment",
            laser_source={
                "pulse_width_min_fs": 300,
                "pulse_width_max_fs": 1000,
                "average_power_min_W": 1,
                "average_power_max_W": 20,
                "frequency_min_kHz": 50,
                "frequency_max_kHz": 500,
            },
            optical_setup={"spot_diameter_um": 20},
            motion_system={"scan_speed_min_mm_s": 10, "scan_speed_max_mm_s": 1000},
            process_capability={"passes_min": 1, "passes_max": 20},
            set_active=True,
        )
    )


def _request():
    return {
        "task_id": "workflow-tgv",
        "session_id": "session-workflow",
        "task_spec": {
            "material": "glass_wafer",
            "material_grade": "TGV",
            "component_type": "TGV_array",
            "process_type": "TGV_drilling",
            "domain_pack": "tgv",
            "geometry": {"wafer_thickness_um": 500, "hole_diameter_um": 50, "pitch_um": 100},
            "targets": {"depth_min_um": 450},
        },
        "question": "TGV 高深径比玻璃通孔加工",
        "display_mode": "research",
    }


def test_complex_workflow_uses_real_tools_and_persists_monotonic_events(isolated_root):
    _equipment()
    client = TestClient(app)
    response = client.post("/workflows/complex_process_task/execute", json=_request())

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["data"]["geometry_model"]["aspect_ratio"] == 10
    assert result["data"]["trial_selection"]["status"] == "TRIAL_MODE_PENDING"
    assert result["data"]["trial_selection"]["trial_mode"] is None
    assert "trial_plan" not in result["data"]
    assert "knowledge_gate_decision" not in result["data"]
    assert "bo_recommendation" not in result["data"]
    assert "execution_plan" not in result["data"]
    sequences = [event["sequence"] for event in result["events"]]
    assert sequences == list(range(1, len(sequences) + 1))
    trace = client.get(f"/execution-traces/{result['run_id']}").json()["events"]
    assert len(trace) == len(result["events"])
    assert [event["sequence"] for event in trace] == sequences
    assert any(event["event_type"] == "tool_started" and event["tool_name"] == "rag_evidence_retrieval" for event in trace)
    assert any(event["event_type"] == "tool_completed" and event["duration_ms"] is not None for event in trace)
    assert all(event["session_id"] == "session-workflow" for event in trace)
    assert all(event["task_id"] == "workflow-tgv" for event in trace)


def test_workflow_ndjson_is_monotonic_and_public(isolated_root):
    _equipment()
    client = TestClient(app)
    response = client.post("/workflows/complex_process_task/stream_ndjson", json=_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["event_type"] == "workflow_started"
    assert events[-1]["event_type"] == "workflow_completed"
    assert [event["render_sequence"] for event in events] == list(range(1, len(events) + 1))
    canonical = [event for event in events if event.get("sequence") is not None]
    assert [event["sequence"] for event in canonical] == sorted(
        {event["sequence"] for event in canonical}
    )
    rendered = response.text.lower()
    assert "chain_of_thought" not in rendered
    assert "hidden_reasoning" not in rendered
    assert "api_key" not in rendered


def test_optical_and_microhole_workflow_definitions_execute(isolated_root):
    _equipment()
    client = TestClient(app)
    optical_request = _request()
    optical_request["task_id"] = "workflow-crl"
    optical_request["task_spec"] = {
        "material": "diamond",
        "component_type": "CRL",
        "process_type": "femtosecond_laser_micromachining",
        "domain_pack": "crl",
        "geometry": {"radius_um": 50, "aperture_um": 300, "lens_count": 10, "surface_count": 2},
    }
    optical = client.post("/workflows/optical_component_task_workflow/execute", json=optical_request)
    microhole = client.post("/workflows/microhole_array_task_workflow/execute", json=_request())

    assert optical.status_code == 200 and optical.json()["status"] == "completed"
    assert optical.json()["data"]["domain_geometry_check"]["geometry_type"] == "dual_paraboloid"
    assert microhole.status_code == 200 and microhole.json()["status"] == "completed"
    assert microhole.json()["data"]["domain_geometry_check"]["aspect_ratio"] == 10


def test_chat_ndjson_adds_monotonic_sequence(isolated_root, monkeypatch):
    monkeypatch.setenv("ULTRAFAST_LLM_PROVIDER", "mock")
    monkeypatch.setenv("ULTRAFAST_LLM_MODEL", "mock")
    client = TestClient(app)
    response = client.post(
        "/chat/stream_ndjson",
        json={"message": "hello", "mode": "normal"},
    )

    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["render_sequence"] for event in events] == list(range(1, len(events) + 1))
    canonical = [event for event in events if event.get("sequence") is not None]
    assert [event["sequence"] for event in canonical] == sorted(
        {event["sequence"] for event in canonical}
    )
