from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.db.session import get_connection


def _create_plan(client: TestClient, task_id: str = "task-tgv") -> dict:
    response = client.post(
        f"/tasks/{task_id}/trial/plans",
        json={
            "task_spec": {
                "process_type": "TGV_drilling",
                "targets": {"depth_min_um": 100},
            },
            "trial_mode": "simple_trial_cut",
            "machine_bounds": {
                "laser_power_W": [1, 10],
                "frequency_kHz": [50, 500],
                "passes": [1, 10],
            },
            "approved_parameter_candidates": [
                {"laser_power_W": 4, "frequency_kHz": 180, "passes": 3},
                {"laser_power_W": 5, "frequency_kHz": 220, "passes": 4},
            ],
            "domain_pack": "tgv",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _execute_and_result(client: TestClient, plan: dict, measurements: dict, defects):
    execution = client.post(
        f"/trial/plans/{plan['trial_plan_id']}/executions",
        json={
            "equipment_revision": "eqrev-1",
            "actual_parameters": plan["parameter_matrix"][0],
            "actual_path": {"type": plan["representative_geometry"]["type"]},
            "monitoring_summary": {"abnormal": False},
        },
    )
    assert execution.status_code == 200, execution.text
    result = client.post(
        f"/trial/executions/{execution.json()['execution_id']}/results",
        json={"measurements": measurements, "defects": defects},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_trial_assess_select_and_pass_unlocks_formal_process(isolated_root):
    client = TestClient(app)
    assessment = client.post(
        "/tasks/task-tgv/trial/assess",
        json={
            "task_spec": {"first_material": True},
            "evidence_status": "insufficient",
            "valid_sample_count": 2,
        },
    )
    assert assessment.status_code == 200
    assert assessment.json()["recommended_mode"] == "simple_trial_cut"
    selection = client.post(
        "/tasks/task-tgv/trial/select",
        json={"assessment": assessment.json(), "trial_mode": "simple_trial_cut"},
    )
    assert selection.status_code == 200
    plan = _create_plan(client)
    assert plan["representative_geometry"]["type"] == "single_hole_or_3x3_array"
    result = _execute_and_result(client, plan, {"depth_um": 120}, [])
    evaluated = client.post(
        f"/trial/results/{result['result_id']}/evaluate",
        json={"reviewer_comment": "meets declared criteria"},
    )

    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evaluation"]["decision"] == "pass"
    assert evaluated.json()["formal_process_decision"]["unlocked"] is True
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM bo_training_sample").fetchone()[0] == 0


def test_missing_measurement_is_conditional_and_requires_confirmation(isolated_root):
    client = TestClient(app)
    plan = _create_plan(client, "task-conditional")
    result = _execute_and_result(client, plan, {}, [])
    evaluated = client.post(
        f"/trial/results/{result['result_id']}/evaluate",
        json={"reviewer_comment": "measurement pending", "confirm_conditional": False},
    )

    assert evaluated.json()["evaluation"]["decision"] == "conditional_pass"
    assert evaluated.json()["formal_process_decision"]["unlocked"] is False


def test_critical_defect_fails_and_skip_plan_cannot_execute(isolated_root):
    client = TestClient(app)
    plan = _create_plan(client, "task-fail")
    result = _execute_and_result(
        client, plan, {"depth_um": 130}, [{"name": "crack", "severity": "critical"}]
    )
    evaluated = client.post(f"/trial/results/{result['result_id']}/evaluate", json={})
    assert evaluated.json()["evaluation"]["decision"] == "fail"
    assert evaluated.json()["formal_process_decision"]["unlocked"] is False

    skipped = client.post(
        "/tasks/task-skip/trial/plans",
        json={"task_spec": {}, "trial_mode": "skip_trial", "machine_bounds": {}},
    ).json()
    response = client.post(
        f"/trial/plans/{skipped['trial_plan_id']}/executions",
        json={"equipment_revision": "eqrev-1"},
    )
    assert response.status_code == 400
