from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_memory.app.api import app
from ultrafast_memory.db.session import get_connection


EVIDENCE = [
    {
        "evidence_id": "candidate-1",
        "source_revision": "source-v1",
        "claim_revision": "claim-v1",
        "claim": "扫描速度范围为 100-200 mm/s",
        "status": "pending_review",
        "parameters": {"scan_speed_mm_s": [100, 200]},
    }
]
EQUIPMENT = {
    "active": True,
    "revision_id": "eqrev-1",
    "machine_bounds": {"scan_speed_mm_s": [10, 1000]},
}
TASK_SPEC = {
    "material": "glass",
    "material_grade": "TGV",
    "process_type": "TGV_drilling",
    "component_type": "TGV_array",
}


def _evaluate(client: TestClient, task_id: str, intended_use: str = "parameter_recommendation", equipment=None):
    return client.post(
        f"/tasks/{task_id}/knowledge/use-gate",
        json={
            "session_id": "session-1",
            "task_spec": TASK_SPEC,
            "intended_use": intended_use,
            "evidence": EVIDENCE,
            "equipment": equipment or EQUIPMENT,
            "proposed_usage": {
                "parameters": [
                    {
                        "candidate_id": "candidate-1",
                        "parameter_name": "scan_speed_mm_s",
                        "lower_bound": 100,
                        "upper_bound": 200,
                        "unit": "mm/s",
                    }
                ]
            },
        },
    )


def test_background_does_not_create_review_decision(isolated_root):
    client = TestClient(app)
    response = _evaluate(client, "task-background", "background_explanation")

    assert response.status_code == 200
    assert response.json()["status"] == "allowed"
    assert "decision_id" not in response.json()
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_usage_decision").fetchone()[0] == 0


def test_parameter_use_creates_at_most_one_aggregated_decision_and_task_approval(isolated_root):
    client = TestClient(app)
    first = _evaluate(client, "task-one")
    second = _evaluate(client, "task-one")

    assert first.json()["status"] == "approval_required"
    assert first.json()["decision_id"] == second.json()["decision_id"]
    assert second.json()["reused_decision"] is True
    approval = client.post(
        f"/knowledge/usage-decisions/{first.json()['decision_id']}/approve-task",
        json={"reviewer_id": "human-1", "comment": "本次任务允许"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["approval_scope"] == "current_task"
    reused = _evaluate(client, "task-one")
    assert reused.json()["status"] == "allowed"
    assert reused.json()["reused_approval"]["approval_id"] == approval.json()["approval_id"]
    other_task = _evaluate(client, "task-two")
    assert other_task.json()["status"] == "approval_required"
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_usage_decision WHERE task_id='task-one'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM process_prior").fetchone()[0] == 0


def test_process_prior_approval_reuses_then_equipment_change_or_revoke_invalidates(isolated_root):
    client = TestClient(app)
    pending = _evaluate(client, "task-prior")
    approval = client.post(
        f"/knowledge/usage-decisions/{pending.json()['decision_id']}/approve-prior",
        json={"reviewer_id": "human-1", "comment": "批准为长期先验"},
    )
    assert approval.status_code == 200, approval.text
    approval_id = approval.json()["approval_id"]
    reusable = _evaluate(client, "task-reuse")
    assert reusable.json()["status"] == "allowed"
    assert reusable.json()["reused_approval"]["approval_id"] == approval_id

    changed_equipment = {**EQUIPMENT, "revision_id": "eqrev-2"}
    invalidated = _evaluate(client, "task-new-equipment", equipment=changed_equipment)
    assert invalidated.json()["status"] == "approval_required"

    revoked = client.post(
        f"/knowledge/usage-approvals/{approval_id}/revoke",
        json={"reviewer_id": "human-1", "comment": "设备状态变化"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    after_revoke = _evaluate(client, "task-after-revoke")
    assert after_revoke.json()["status"] == "approval_required"
    with get_connection() as connection:
        prior = connection.execute("SELECT status FROM process_prior").fetchone()
        assert prior["status"] == "revoked"
        assert connection.execute("SELECT COUNT(*) FROM knowledge_review_action").fetchone()[0] == 2


def test_review_bundle_is_limited_to_five_items(isolated_root):
    client = TestClient(app)
    evidence = [
        {**EVIDENCE[0], "evidence_id": f"candidate-{index}", "claim_revision": f"claim-{index}"}
        for index in range(7)
    ]
    response = client.post(
        "/tasks/task-bundle/knowledge/use-gate",
        json={
            "task_spec": TASK_SPEC,
            "intended_use": "bo_search_bound",
            "evidence": evidence,
            "equipment": EQUIPMENT,
            "proposed_usage": {},
        },
    )

    assert response.json()["truncated_evidence_count"] == 2
    decision = client.get(f"/knowledge/usage-decisions/{response.json()['decision_id']}").json()
    assert len(decision["evidence_ids"]) == 5
