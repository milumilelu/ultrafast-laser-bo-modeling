from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ultrafast_memory.app.api import app
from ultrafast_memory.demo.service import DemoService
import sqlite3


def test_doctor_reports_core_health_without_external_call(isolated_root):
    client = TestClient(app)
    response = client.get("/doctor")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["readiness"] == "READY FOR DEMO"
    assert body["external_call_performed"] is False
    checks = {item["name"]: item for item in body["checks"]}
    assert {
        "dependencies",
        "database",
        "write_access",
        "port",
        "equipment",
        "rag",
        "llm",
        "bo",
        "demo_fixtures",
    }.issubset(checks)
    assert checks["database"]["status"] == "pass"
    assert checks["bo"]["status"] == "pass"
    assert checks["bo"]["details"]["adapter_placeholder"] is False


def test_task_report_writes_markdown_json_and_database_record(isolated_root):
    client = TestClient(app)
    response = client.post(
        "/tasks/report-task/reports",
        json={
            "payload": {
                "task_spec": {
                    "objective": "TGV demo",
                    "material": "glass",
                    "component_type": "TGV_array",
                    "process_type": "TGV_drilling",
                },
                "equipment": {"profile_name": "demo", "revision_id": "eq-1", "machine_bounds": {}},
                "evidence_pack": {"evidence_status": "sufficient", "citations": [{"internal": "[demo]"}]},
                "process_route": {"steps": ["trial", "measure"]},
                "trial_plan": {"trial_mode": "simple_trial_cut", "representative_geometry": {"type": "3x3"}},
                "knowledge_gate_decision": {"status": "allowed"},
                "bo_recommendation": {"model_status": "rule_based_cold_start", "sample_count": 0, "recommended_parameters": {}},
                "quality_plan": {"metrics": ["taper_deg"]},
                "next_step": "run trial",
            }
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "parameter_window_and_source" in body["report"]
    assert "equipment_clipping" in body["report"]
    markdown = Path(body["markdown_path"])
    json_path = Path(body["json_path"])
    assert markdown.exists() and json_path.exists()
    assert "rule_based_cold_start" in markdown.read_text(encoding="utf-8")
    latest = client.get("/tasks/report-task/reports/latest")
    assert latest.status_code == 200
    assert latest.json()["content_hash"] == body["content_hash"]


def test_demo_waits_for_explicit_review_then_completes_offline(isolated_root):
    client = TestClient(app)
    mode = client.post("/demo/tgv/run", json={"approve_review": False})
    assert mode.json()["status"] == "waiting_trial_mode"
    waiting = client.post("/demo/tgv/run", json={"approve_review": False, "selected_trial_mode": "simple_trial_cut"})

    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["status"] == "waiting_review"
    assert waiting.json()["approval_card"]["actions"] == ["approve_task", "approve_prior", "reject"]
    assert waiting.json()["external_network"] is False
    assert waiting.json()["llm_call_performed"] is False

    completed = client.post("/demo/tgv/run", json={"approve_review": True, "selected_trial_mode": "simple_trial_cut"})
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["bo"]["model_status"] == "rule_based_cold_start"
    assert body["trial_result"]["evaluation"]["decision"] == "pass"
    assert body["formal_execution"]["status"] == "ready"
    assert body["report"]["status"] == "completed"
    assert body["external_network"] is False and body["llm_call_performed"] is False


def test_demo_degrades_to_nonpersistent_preview_for_readonly_database(
    isolated_root, monkeypatch
):
    service = DemoService()
    monkeypatch.setattr(
        service.fixtures,
        "ensure_tgv_evidence",
        lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("attempt to write a readonly database")
        ),
    )

    result = service.run_tgv(approve_review=True)

    assert result["status"] == "read_only_demo"
    assert result["persistence_performed"] is False
    assert result["trial_plan"]["parameter_matrix"] == []
    assert any("parameter matrix is empty" in item for item in result["trial_plan"]["warnings"])
    assert result["knowledge_gate"]["status"] == "blocked"
    assert result["formal_execution"]["formal_process_unlocked"] is False
    assert result["external_network"] is False and result["llm_call_performed"] is False
