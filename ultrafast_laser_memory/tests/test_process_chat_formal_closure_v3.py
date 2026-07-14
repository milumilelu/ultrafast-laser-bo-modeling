from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.session_state import update_session_state
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.trial.service import TrialApplicationService


def _post(client: TestClient, session_id: str, message: str) -> dict:
    response = client.post("/chat", json={"session_id": session_id, "message": message, "use_skills": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_chat_continues_from_verified_trial_through_formal_archive(isolated_root):
    client = TestClient(app)
    session_id = client.post("/chat/sessions", json={}).json()["session_id"]
    plan = TrialApplicationService().create_plan("process-" + session_id, {
        "task_spec": {"process_type": "cutting", "targets": {}},
        "trial_mode": "simple_trial_cut", "machine_bounds": {"laser_power_W": [1, 5]},
        "approved_parameter_candidates": [{"laser_power_W": 2}], "domain_pack": "surface_texturing"})
    task = {"material": "CFRP_T300", "process_type": "cutting", "thickness_mm": 5,
            "quality_requirement": "no_delamination", "cut_length_mm": 100,
            "efficiency_requirement": "none", "auxiliary": "compressed_air", "layer_cut_allowed": True}
    update_session_state(session_id, {"active_workflow": "complex_process_task", "active_skill": "complex_process_task",
        "workflow_stage": "trial_result_pending", "pending_questions": ["trial_result"],
        "collected_slots": {"process_task_spec": task, "process_workflow": {
            "state": "TRIAL_RESULT_PENDING", "selected_trial_mode": "simple_trial_cut", "trial_plan": plan,
            "parameter_recommendation": {"recommendation_id": "explore-1"}}}})

    trial = _post(client, session_id, '{"equipment_revision":"r1","material_batch":"batch-1",'
                  '"actual_parameters":{"laser_power_W":2},"parameter_units":{"laser_power_W":"W"},'
                  '"actual_path":{"type":"coupon"},"measurements":{"cut_complete":1},"defects":[],'
                  '"files":["trial_edge.jpg"]}')
    assert trial["current_stage"] == "FORMAL_PROCESS_READY"
    assert trial["workflow_state"]["business_state"] == "READY_FOR_EXTERNAL_PROCESS"
    assert trial["next_required_action"]["action_type"] == "submit_formal_preflight"

    started = _post(client, session_id,
                    '{"equipment_revision":"r1","material_batch":"batch-1","operator_confirmation":true}')
    assert started["current_stage"] == "FORMAL_PROCESS_RUNNING"
    assert started["workflow_state"]["business_state"] == "WAITING_EXTERNAL_RESULT"
    assert "系统未连接、控制或监控设备" in started["assistant_message"]
    checkpoint = _post(client, session_id,
                       '{"progress_percent":100,"deviation_level":0,"observation":{"delamination":false}}')
    assert checkpoint["current_stage"] == "FINAL_INSPECTION_PENDING"
    assert checkpoint["workflow_state"]["business_state"] == "QUALITY_REVIEW"
    closed = _post(client, session_id,
        '{"required_metrics":["delamination_width"],"measurements":{"delamination_width":0},'
        '"constraint_results":{"no_delamination":true},"files":["edge_photo.jpg"]}')
    assert closed["current_stage"] == "COMPLETED"
    assert closed["workflow_state"]["business_state"] == "COMPLETED"
    assert closed["workflow_state"]["report"]["report"]["business_state"] == "COMPLETED"
    assert closed["next_required_action"]["blocking"] is False
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM formal_process_plan").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM formal_process_execution").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM experiment_record").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM task_report").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM optimization_campaign").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM optimization_iteration").fetchone()[0] == 1
