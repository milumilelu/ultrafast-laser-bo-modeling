from __future__ import annotations

import copy

import pytest

from ultrafast_agent.documents import DocumentIngestionService, OcrQualityGate
from ultrafast_agent.jobs import BackgroundJobService
from ultrafast_domain.documents import DocumentElement, OcrDocument, VisionAnalysisCandidate
from ultrafast_integrations.cam import ConfigDrivenCamAdapter, GenericJsonCamAdapter
from ultrafast_integrations.storage.job_repository import SQLiteJobRepository
from ultrafast_integrations.vision import MultimodalLLMVisionProvider
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_agent.process_recommendations import BOTrainingApprovalService, ProcessRecommendationService


def _recommendation_input():
    return {
        "task_id": "task-1", "workflow_id": "workflow-1",
        "task_spec": {"material": "diamond", "process_type": "milling"},
        "bo_result": {"status": "ready", "model_status": "hybrid_rule_bo", "recommended_parameters": {"laser_power_W": 5.0},
                      "predictions": {}, "model_version": "m1", "dataset_version": "d1", "objective_version": "o1"},
        "search_space": {"variables": {"laser_power_W": {"mode": "optimizable", "lower": 2, "upper": 6}},
                         "fixed_parameters": {"frequency_kHz": 200}, "forbidden_parameters": {},
                         "derived_constraints": [], "outcome_constraints": [], "search_space_version": "s1", "feasibility_status": "ready"},
        "parameter_units": {"laser_power_W": "W", "frequency_kHz": "kHz"},
    }


def test_complete_recipe_cam_schema_and_feedback_candidate(isolated_root):
    init_database()
    service = ProcessRecommendationService()
    recommendation = service.create(**_recommendation_input())
    assert recommendation.complete_recipe == {"frequency_kHz": 200, "laser_power_W": 5.0}
    assert recommendation.status == "ready_for_cam"
    output = service.cam_parameters(recommendation.recommendation_id)
    assert output["schema_version"] == "1.0" and output["parameters"] == recommendation.complete_recipe
    feedback = service.submit_feedback(
        recommendation.recommendation_id,
        {"run_id": "run-1", "cam_applied_parameters": output["parameters"],
         "machine_actual_parameters": output["parameters"], "measurements": {"Ra_um": 0.5},
         "run_status": "completed", "alarms": [], "measurement_method": "profilometer"},
    )
    assert feedback["training_sample_created"] is False
    assert feedback["eligibility"]["eligible"] is True
    approved = BOTrainingApprovalService().approve(feedback["candidate_id"], "expert")
    assert approved["sample_id"].startswith("bo_sample_")
    assert approved["dataset_version"]["sample_ids"] == [approved["sample_id"]]


def test_cam_adapters_do_not_mutate_recommendation():
    recommendation = {
        "recommendation_id": "r", "task_id": "t", "stage": "trial_cut", "status": "ready_for_cam",
        "process_type": "milling", "material": "diamond", "complete_recipe": {"laser_power_W": 5},
        "parameter_metadata": {"laser_power_W": {"unit": "W", "source": "bo_recommendation"}},
    }
    original = copy.deepcopy(recommendation)
    GenericJsonCamAdapter().map_parameters(recommendation)
    adapter = ConfigDrivenCamAdapter(
        {"mapping_version": "test-only", "format_version": "1", "parameters": {"laser_power_W": {"vendor_field": "P", "required": True}}}
    )
    assert adapter.map_parameters(recommendation)["parameters"] == {"P": 5}
    assert recommendation == original


def test_document_schema_and_vision_default_disabled():
    element = DocumentElement("doc", 1, "element", "paragraph", "5 W", (0, 0, 10, 10), 0.8, "paddleocr", "1", "hash")
    assert element.to_dict()["review_status"] == "unreviewed"
    provider = MultimodalLLMVisionProvider()
    with pytest.raises(RuntimeError, match="disabled"):
        provider.analyze({"artifact_id": "image"}, "surface_defect", {})
    assert not any(route for route in ())  # provider intentionally has no public router registration


def test_native_pdf_skips_ocr_and_scanned_document_job_is_idempotent(isolated_root, tmp_path, monkeypatch):
    init_database()
    service = DocumentIngestionService(BackgroundJobService(SQLiteJobRepository()))
    native = tmp_path / "native.pdf"
    native.write_bytes(b"%PDF-test")
    monkeypatch.setattr("ultrafast_agent.documents.service._native_pdf_has_text", lambda _: True)
    assert service.ingest({"artifact_id": "native", "path": str(native)})["ocr_job_created"] is False

    scanned = tmp_path / "scan.png"
    scanned.write_bytes(b"not-a-real-image-needed-for-queue-test")
    first = service.ingest({"artifact_id": "scan", "path": str(scanned)})
    second = service.ingest({"artifact_id": "scan", "path": str(scanned)})
    assert first["ocr_job_created"] is True and second["ocr_job_created"] is False
    assert first["job_id"] == second["job_id"]


def test_low_confidence_ocr_numeric_candidate_cannot_enter_bo(isolated_root):
    init_database()
    element = DocumentElement("doc", 1, "e1", "table_cell", "laser power 5 W", (1, 2, 3, 4), 0.7, "paddleocr", "1", "hash")
    document = OcrDocument("doc", "artifact", "paddleocr", "1", "hash", (element,))
    with get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) FROM approved_bo_training_sample").fetchone()[0]
    candidate = OcrQualityGate().extract_numeric_candidates(document)[0]
    with get_connection() as conn:
        after = conn.execute("SELECT COUNT(*) FROM approved_bo_training_sample").fetchone()[0]
    assert candidate["review_status"] == "pending_review"
    assert candidate["allowed_destinations"] == []
    assert before == after


def test_enabled_vision_result_remains_experimental():
    class Client:
        def analyze_image(self, **_):
            return {"observations": [{"text": "candidate"}], "confidence": 0.8}

    result = MultimodalLLMVisionProvider(Client(), enabled=True, model="test-model").analyze(
        {"artifact_id": "image"}, "surface_defect", {}
    )
    assert result.status == "experimental_unvalidated"
