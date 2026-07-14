from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.legacy_status_parser import LegacyTaskSpecAdapter


def test_normal_chat_never_uses_legacy_projection(isolated_root, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("legacy projection entered normal chat")

    monkeypatch.setattr(LegacyTaskSpecAdapter, "adapt", fail)
    response = TestClient(app).post("/chat", json={
        "message": "切割2mm厚的碳纤维复合板",
        "use_skills": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["progress"]["progress_percent"] is None
    assert body["progress"]["current_stage"] == "ask_user"
    assert body["evidence_gap"] is None
    assert body["workflow_state"]["runtime_mode"] == "capability_discovery"
    assert not any(item.get("stage") == "evidence_gap_checking" for item in body["execution_trace"])
