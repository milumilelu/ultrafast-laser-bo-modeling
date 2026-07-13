from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ultrafast_agent.task_intake import (
    HybridTaskFieldExtractionService,
    TaskFieldNormalizer,
    TaskFieldValidator,
    TaskSpecMergeService,
)
from ultrafast_agent.task_intake.deterministic_extractor import ContextualDeterministicExtractor
from ultrafast_agent.task_intake.schemas import ClarificationContext, TaskFieldCandidate, TaskSpecPatch
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate
from ultrafast_memory.equipment.service import create_equipment_profile


def _context(*pending: str, process: str = "cutting") -> ClarificationContext:
    return ClarificationContext(
        workflow_type="complex_process_task",
        stage="REQUIREMENTS_PENDING",
        clarification_round=2,
        pending_fields=list(pending),
        ordered_fields=list(pending),
        expected_answer_types={field: "test" for field in pending},
    )


def _pipeline(message: str, current: dict, context: ClarificationContext, client=None):
    patch = HybridTaskFieldExtractionService(client).extract(message, current, context)
    patch = TaskFieldNormalizer.normalize(patch)
    patch = TaskFieldValidator.validate(patch, current, context)
    return patch, TaskSpecMergeService.merge(current, patch, context=context, message_id="msg_test")


def _equipment() -> None:
    create_equipment_profile(EquipmentProfileCreate(
        profile_name="hybrid intake test laser",
        set_active=True,
        laser_source={
            "pulse_width_min_fs": 500,
            "pulse_width_max_fs": 8000,
            "average_power_min_W": 0.1,
            "average_power_max_W": 5.33,
            "frequency_min_kHz": 2,
            "frequency_max_kHz": 200,
        },
        optical_setup={"spot_diameter_um": 5, "focus_control_mode": "automatic_z"},
        motion_system={"scan_speed_min_mm_s": 1, "scan_speed_max_mm_s": 200},
    ))


def _session(client: TestClient, title: str | None = None) -> str:
    return client.post("/chat/sessions", json={"title": title} if title else {}).json()["session_id"]


def _chat(client: TestClient, session_id: str, message: str) -> dict:
    response = client.post(
        "/chat",
        json={"session_id": session_id, "message": message, "use_skills": True},
    )
    assert response.status_code == 200
    return response.json()


def _stream(client: TestClient, session_id: str, message: str) -> list[dict]:
    response = client.post(
        "/chat/stream_ndjson",
        json={"session_id": session_id, "message": message, "use_skills": True, "stream": True},
    )
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_cutting_clarification_log_regression(isolated_root):
    _equipment()
    client = TestClient(app)
    session_id = _session(client)
    _chat(client, session_id, "切割5mm厚型号为T300的碳纤维复合板")
    result = _chat(client, session_id, "切缝区域无分层;100mm直线；无效率要求；压缩空气；允许")

    state = result["workflow_state"]
    task = state["task_spec"]
    assert task["thickness_mm"] == 5
    assert task["cut_length_mm"] == 100
    assert task["contour_type"] == "straight"
    assert task["layer_cut_allowed"] is True
    assert state["missing_slots"] == []
    assert state["field_provenance"]["cut_length_mm"]["evidence"] == "100mm"
    assert state["field_provenance"]["cut_length_mm"]["source"] == "contextual_deterministic"
    assert state["field_provenance"]["cut_length_mm"]["extractor_version"] == "hybrid-slot-v1"
    event_types = {item["event_type"] for item in result["execution_trace"]}
    assert "field_candidate_extracted" in event_types
    assert "task_spec_patched" in event_types


def test_contextual_boolean_short_answer_is_accepted():
    current = {"process_type": "cutting"}
    patch, merged = _pipeline("允许", current, _context("layer_cut_allowed"))
    assert patch.updates[0].field_name == "layer_cut_allowed"
    assert merged.task_spec["layer_cut_allowed"] is True


def test_cut_length_does_not_silently_overwrite_thickness():
    current = {"process_type": "cutting", "thickness_mm": 5}
    patch, merged = _pipeline("100mm直线", current, _context("cut_length_mm"))
    assert all(item.field_name != "thickness_mm" for item in patch.updates)
    assert merged.task_spec["thickness_mm"] == 5
    assert merged.task_spec["cut_length_mm"] == 100


def test_fill_conflict_is_blocked_and_explicit_correction_is_revisioned():
    current = {"process_type": "cutting", "thickness_mm": 5}
    fill = TaskSpecPatch(updates=[TaskFieldCandidate(
        field_name="thickness_mm",
        raw_value=100,
        normalized_value=100,
        unit="mm",
        evidence="100mm",
        extraction_source="legacy_regex",
        confidence=0.6,
        operation="fill",
    )])
    blocked = TaskSpecMergeService.merge(current, fill, message_id="msg_fill", context=_context())
    assert blocked.task_spec["thickness_mm"] == 5
    assert blocked.conflicts[0]["reason"] == "confirmed_value_requires_explicit_correction"

    _, corrected = _pipeline("板厚改为6mm", current, _context())
    assert corrected.task_spec["thickness_mm"] == 6
    assert corrected.revision_history[0]["old_value"] == 5
    assert corrected.revision_history[0]["new_value"] == 6


def test_ambiguous_short_answer_is_not_arbitrarily_assigned():
    current = {"process_type": "cutting"}
    deterministic = ContextualDeterministicExtractor().extract(
        "无要求",
        current,
        _context("efficiency_requirement", "auxiliary"),
    )
    assert deterministic.updates == []
    assert deterministic.ambiguities


@pytest.mark.parametrize(("raw", "unit", "expected"), [
    (10, "cm", 100),
    (1000, "um", 1),
])
def test_length_units_are_normalized_to_mm(raw, unit, expected):
    patch = TaskSpecPatch(updates=[TaskFieldCandidate(
        field_name="cut_length_mm",
        raw_value=raw,
        unit=unit,
        evidence=f"{raw}{unit}",
        extraction_source="contextual_deterministic",
        confidence=0.99,
    )])
    normalized = TaskFieldNormalizer.normalize(patch)
    assert normalized.updates[0].normalized_value == expected
    assert normalized.updates[0].unit == "mm"


def test_llm_uses_strict_schema_and_valid_output_enters_patch():
    class StructuredClient:
        provider = "test"

        def __init__(self):
            self.calls = []

        def chat(self, *args, **kwargs):
            self.calls.append(kwargs)
            return {"content": json.dumps({
                "updates": [
                    {
                        "field_name": "cut_length_mm",
                        "raw_value": 100,
                        "unit": "mm",
                        "evidence": "一百毫米",
                        "confidence": 0.98,
                        "operation": "fill",
                    },
                    {
                        "field_name": "layer_cut_allowed",
                        "raw_value": True,
                        "unit": None,
                        "evidence": "允许",
                        "confidence": 0.98,
                        "operation": "fill",
                    },
                ],
                "unresolved_fields": [],
                "ambiguities": [],
            })}

    client = StructuredClient()
    current = {"process_type": "cutting", "thickness_mm": 5}
    patch, merged = _pipeline("总共走刀一百毫米；允许", current, _context("cut_length_mm", "layer_cut_allowed"), client)
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    assert patch.llm_attempted is True
    assert merged.task_spec["cut_length_mm"] == 100
    assert merged.task_spec["layer_cut_allowed"] is True


@pytest.mark.parametrize("client", [
    pytest.param(type("TimeoutClient", (), {
        "provider": "test",
        "chat": lambda self, *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timeout")),
    })(), id="timeout"),
    pytest.param(type("NonJsonClient", (), {
        "provider": "test",
        "chat": lambda self, *args, **kwargs: {"content": "not-json"},
    })(), id="non-json"),
])
def test_llm_failure_degrades_without_state_pollution(client):
    current = {"process_type": "cutting", "thickness_mm": 5}
    patch, merged = _pipeline("边缘质量要尽可能干净", current, _context("quality_requirement"), client)
    assert patch.degraded is True
    assert patch.llm_attempted is True
    assert merged.task_spec == current


def test_llm_cannot_inject_unallowed_process_parameter():
    class DisallowedClient:
        provider = "test"

        def chat(self, *args, **kwargs):
            return {"content": json.dumps({
                "updates": [{
                    "field_name": "laser_power_W",
                    "raw_value": 20,
                    "unit": "W",
                    "evidence": "20W",
                    "confidence": 0.99,
                    "operation": "fill",
                }],
                "unresolved_fields": ["quality_requirement"],
                "ambiguities": [],
            })}

    current = {"process_type": "cutting", "thickness_mm": 5}
    patch, merged = _pipeline("质量未知，20W只是设备铭牌", current, _context("quality_requirement"), DisallowedClient())
    assert patch.updates == []
    assert patch.rejected_candidates[0]["reason"] == "field_not_allowed"
    assert "laser_power_W" not in merged.task_spec
    assert merged.task_spec == current


def test_parser_stall_stops_repeating_identical_question(isolated_root):
    _equipment()
    client = TestClient(app)
    session_id = _session(client)
    first = _chat(client, session_id, "切割5mm厚型号为T300的碳纤维复合板")
    assert first["workflow_state"]["current_stage_code"] == "REQUIREMENTS_PENDING"
    _chat(client, session_id, "无法识别的回答")
    stalled = _chat(client, session_id, "无法识别的回答")
    assert stalled["workflow_state"]["current_stage_code"] == "PARSER_STALL"
    assert "系统未能可靠解析" in stalled["assistant_message"]
    assert "字段化格式" in stalled["assistant_message"]
    assert stalled["workflow_state"]["task_spec"]["thickness_mm"] == 5
    assert stalled["next_required_action"]["action_type"] == "submit_structured_fields"


def test_stream_and_non_stream_workflow_state_are_consistent(isolated_root):
    _equipment()
    client = TestClient(app)
    normal_session = _session(client, "normal-hybrid-intake")
    stream_session = _session(client, "stream-hybrid-intake")
    first = "切割5mm厚型号为T300的碳纤维复合板"
    second = "切缝区域无分层;100mm直线；无效率要求；压缩空气；允许"
    _chat(client, normal_session, first)
    normal = _chat(client, normal_session, second)["workflow_state"]
    _stream(client, stream_session, first)
    stream_events = _stream(client, stream_session, second)
    streamed = next(item for item in stream_events if item.get("type") == "workflow_state")
    assert streamed["task_spec"] == normal["task_spec"]
    assert streamed["missing_slots"] == normal["missing_slots"]
    assert streamed["current_stage_code"] == normal["current_stage_code"]


def test_workflow_status_has_no_general_semantic_parser(project_root: Path):
    source = (project_root / "src/ultrafast_memory/chat/workflow_status.py").read_text(encoding="utf-8")
    assert "def parse_process_task_fields" not in source
    assert "def _parse_task" not in source
    assert "task.update(parse_process_task_fields" not in source
