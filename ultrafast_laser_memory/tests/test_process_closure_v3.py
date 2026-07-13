from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.process_workflow.closure import archive_gate, bo_sample_eligibility, quality_decision


def test_incomplete_inspection_is_inconclusive_and_cannot_close():
    result = quality_decision(["delamination_width", "kerf_width"], {"kerf_width": 1}, {})
    assert result["decision"] == "inconclusive"
    assert not result["can_close"]


def test_invalid_result_cannot_enter_bo_and_archive_needs_report():
    assert not bo_sample_eligibility({"validation_status": "invalid"})["eligible"]
    allowed, missing = archive_gate(quality_decided=True, report_generated=False, experiment_record_validated=True)
    assert not allowed and missing == ["task_report"]


def test_formal_release_api_is_fail_closed(isolated_root):
    response = TestClient(app).post("/process-workflow/formal/release-gate", json={})
    assert response.status_code == 200
    assert response.json()["decision"] == "blocked"


def test_formal_process_api_requires_release_preflight_and_final_inspection(isolated_root):
    client = TestClient(app)
    released = client.post("/tasks/t1/formal-process/release", json={
        "trial_passed": True, "source_types": ["verified_experiment"],
        "equipment_revision_matches": True, "equipment_revision": "r1"}).json()
    preflight = client.post("/tasks/t1/formal-process/preflight", json={
        "plan_id": released["plan_id"], "equipment_revision": "r1", "material_batch": "b1",
        "operator_confirmation": True}).json()
    started = client.post("/tasks/t1/formal-process/start", json={
        "plan_id": released["plan_id"], "preflight_status": preflight["status"]}).json()
    execution_id = started["execution_id"]
    finished = client.post(f"/formal-process/executions/{execution_id}/finish").json()
    assert finished["status"] == "finished"
    assert finished["next_required_action"] == "submit_final_inspection"
    inspection = client.post(f"/formal-process/executions/{execution_id}/inspection", json={
        "required_metrics": ["delamination"], "measurements": {}}).json()
    assert inspection["completeness_status"] == "incomplete"


def test_formal_adjustment_is_restricted_to_three_way_trust_region(isolated_root):
    response = TestClient(app).post("/process-workflow/formal/local-adjustment", json={
        "approved_window": {"power": [2, 4]}, "equipment_bounds": {"power": [1, 5]},
        "local_trust_region": {"power": [2.5, 3.5]}, "proposed_parameters": {"power": 4}})
    assert response.json()["decision"] == "blocked"
    assert response.json()["effective_trust_region"] == {"power": [2.5, 3.5]}
