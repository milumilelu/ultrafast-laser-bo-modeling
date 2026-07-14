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


def test_active_legacy_workflow_does_not_capture_a_new_side_question(isolated_root):
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

    response = _post(client, session_id, "先别管这个，我想查一下金刚石烧蚀机制")
    assert response["selected_skill"] == "evidence_research"
    assert response["workflow_state"]["task_spec"] == task
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM formal_process_execution").fetchone()[0] == 0
