from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
def test_normal_chat_uses_event_projection_only(isolated_root, project_root):
    response = TestClient(app).post("/chat", json={
        "message": "切割2mm厚的碳纤维复合板",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["progress"]["progress_percent"] is None
    assert body["progress"]["current_stage"] == "final_answer"
    assert body["evidence_gap"] is None
    assert body["workflow_state"]["runtime_mode"] == "capability_discovery"
    assert not any(item.get("stage") == "evidence_gap_checking" for item in body["execution_trace"])
    chat_root = project_root / "src/ultrafast_memory/chat"
    assert not (chat_root / "legacy_status_parser.py").exists()
    assert not (chat_root / "legacy_projection_adapter.py").exists()
    assert not (chat_root / "workflow_projection.py").exists()
    service_source = (chat_root / "service.py").read_text(encoding="utf-8")
    assert "complex_process_task" not in service_source
    assert "TaskWorkflowService" not in service_source
    default_config = (project_root / "configs/default.yaml").read_text(encoding="utf-8")
    assert 'runtime_mode: "capability_discovery"' in default_config
    assert "default_workflow" not in default_config


def test_removed_dual_mode_flag_is_rejected(isolated_root):
    response = TestClient(app).post("/chat", json={
        "message": "hello",
        "use_skills": False,
    })

    assert response.status_code == 422
