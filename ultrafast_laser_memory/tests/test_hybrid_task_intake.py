from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ultrafast_agent.task_intake import (
    StrictKeyValueParser,
    TaskFieldExtractionService,
    TaskFieldNormalizer,
    TaskSpecPatchValidator,
    TaskSpecMergeService,
)
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
    patch = TaskFieldExtractionService(client).extract(message, current, context)
    patch = TaskFieldNormalizer.normalize(patch)
    patch = TaskSpecPatchValidator.validate(patch, current, context, user_message=message)
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


class ScriptedTaskIntakeLLM:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        prompt = messages[-1]["content"]
        if "切割3mm厚的碳纤维复合板" in prompt:
            updates = [
                _llm_update("process_type", "cutting", "切割"),
                _llm_update("material", "CFRP", "碳纤维复合板"),
                _llm_update("thickness_mm", 3, "3mm", unit="mm"),
            ]
        elif "切割5mm厚型号为T300的碳纤维复合板" in prompt:
            updates = [
                _llm_update("process_type", "cutting", "切割"),
                _llm_update("material", "CFRP_T300", "T300"),
                _llm_update("thickness_mm", 5, "5mm", unit="mm"),
            ]
        elif "切缝区域无分层；100mm，直线；无；压缩空气；允许" in prompt:
            updates = [
                _llm_update("quality_requirement", "no_delamination", "切缝区域无分层"),
                _llm_update("cut_length_mm", 100, "100mm", unit="mm"),
                _llm_update("contour_type", "straight", "直线"),
                _llm_update("efficiency_requirement", "none", "无"),
                _llm_update("auxiliary", "compressed_air", "压缩空气"),
                _llm_update("layer_cut_allowed", True, "允许"),
            ]
        elif "切缝区域无分层;100mm直线；无效率要求；压缩空气；允许" in prompt:
            updates = [
                _llm_update("quality_requirement", "no_delamination", "切缝区域无分层"),
                _llm_update("cut_length_mm", 100, "100mm", unit="mm"),
                _llm_update("contour_type", "straight", "直线"),
                _llm_update("efficiency_requirement", "none", "无效率要求"),
                _llm_update("auxiliary", "compressed_air", "压缩空气"),
                _llm_update("layer_cut_allowed", True, "允许"),
            ]
        else:
            updates = []
        return {"content": json.dumps({
            "updates": updates,
            "unresolved_fields": [],
            "ambiguities": [],
        }, ensure_ascii=False)}


class StaticTaskIntakeLLM:
    provider = "test"
    model = "task-intake-test"

    def __init__(self, updates=None, ambiguities=None):
        self.updates = list(updates or [])
        self.ambiguities = list(ambiguities or [])
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return {"content": json.dumps({
            "updates": self.updates,
            "unresolved_fields": [],
            "ambiguities": self.ambiguities,
            "extractor_version": "llm-task-intake-v1",
        }, ensure_ascii=False)}


def _llm_update(field, value, evidence, unit=None, operation="fill"):
    return {
        "field_name": field,
        "raw_value": value,
        "unit": unit,
        "evidence": evidence,
        "confidence": 0.99,
        "operation": operation,
    }


def test_llm_primary_real_log_with_comma_and_contextual_short_answers(isolated_root, monkeypatch):
    _equipment()
    llm = ScriptedTaskIntakeLLM()
    monkeypatch.setattr(
        "ultrafast_memory.process_workflow.chat_orchestrator.create_llm_client",
        lambda config: llm,
    )
    client = TestClient(app)
    session_id = _session(client, "llm-primary-real-log")

    _chat(client, session_id, "切割3mm厚的碳纤维复合板")
    result = _chat(client, session_id, "切缝区域无分层；100mm，直线；无；压缩空气；允许")

    task = result["workflow_state"]["task_spec"]
    assert task["thickness_mm"] == 3
    assert task["cut_length_mm"] == 100
    assert task["contour_type"] == "straight"
    assert task["efficiency_requirement"] == "none"
    assert task["auxiliary"] == "compressed_air"
    assert task["layer_cut_allowed"] is True
    assert result["workflow_state"]["missing_slots"] == []
    assert llm.calls == 2


def test_cutting_clarification_log_regression(isolated_root, monkeypatch):
    _equipment()
    llm = ScriptedTaskIntakeLLM()
    monkeypatch.setattr(
        "ultrafast_memory.process_workflow.chat_orchestrator.create_llm_client",
        lambda config: llm,
    )
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
    assert state["field_provenance"]["cut_length_mm"]["source"] == "llm_semantic_extraction"
    assert state["field_provenance"]["cut_length_mm"]["extractor_version"] == "llm-task-intake-v1"
    assert state["field_extraction"]["provider"] == "deepseek"
    assert state["field_extraction"]["model"] == "deepseek-v4-flash"
    assert state["field_extraction"]["missing_fields"] == []
    event_types = {item["event_type"] for item in result["execution_trace"]}
    assert "field_candidate_extracted" in event_types
    assert "task_spec_patched" in event_types


def test_contextual_boolean_short_answer_is_accepted():
    current = {"process_type": "cutting"}
    client = StaticTaskIntakeLLM([_llm_update("layer_cut_allowed", True, "允许")])
    patch, merged = _pipeline("允许", current, _context("layer_cut_allowed"), client)
    assert patch.updates[0].field_name == "layer_cut_allowed"
    assert merged.task_spec["layer_cut_allowed"] is True
    assert len(client.calls) == 1


def test_cut_length_does_not_silently_overwrite_thickness():
    current = {"process_type": "cutting", "thickness_mm": 5}
    client = StaticTaskIntakeLLM([
        _llm_update("cut_length_mm", 100, "100mm", unit="mm"),
        _llm_update("contour_type", "straight", "直线"),
    ])
    patch, merged = _pipeline("100mm直线", current, _context("cut_length_mm"), client)
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

    client = StaticTaskIntakeLLM([
        _llm_update("thickness_mm", 6, "板厚改为6mm", unit="mm", operation="correct"),
    ])
    _, corrected = _pipeline("板厚改为6mm", current, _context(), client)
    assert corrected.task_spec["thickness_mm"] == 6
    assert corrected.revision_history[0]["old_value"] == 5
    assert corrected.revision_history[0]["new_value"] == 6


def test_ambiguous_short_answer_is_not_arbitrarily_assigned():
    current = {"process_type": "cutting"}
    client = StaticTaskIntakeLLM(ambiguities=[{"reason": "ambiguous_short_answer"}])
    patch, merged = _pipeline(
        "无要求", current, _context("efficiency_requirement", "auxiliary"), client
    )
    assert patch.updates == []
    assert patch.ambiguities
    assert merged.task_spec == current


def test_free_natural_language_answer_uses_llm_semantics():
    message = "我主要要求切缝不要分层，长度大概100毫米，时间无所谓，用压缩空气辅助，可以多次分层切割。"
    client = StaticTaskIntakeLLM([
        _llm_update("quality_requirement", "no_delamination", "切缝不要分层"),
        _llm_update("cut_length_mm", 100, "100毫米", unit="毫米"),
        _llm_update("efficiency_requirement", "none", "时间无所谓"),
        _llm_update("auxiliary", "compressed_air", "压缩空气"),
        _llm_update("layer_cut_allowed", True, "可以多次分层切割"),
    ])
    patch, merged = _pipeline(
        message,
        {"process_type": "cutting"},
        _context(
            "quality_requirement", "cut_length_mm", "efficiency_requirement",
            "auxiliary", "layer_cut_allowed",
        ),
        client,
    )
    assert patch.extraction_mode == "llm_structured"
    assert merged.task_spec["quality_requirement"] == "no_delamination"
    assert merged.task_spec["cut_length_mm"] == 100
    assert merged.task_spec["efficiency_requirement"] == "none"
    assert merged.task_spec["auxiliary"] == "compressed_air"
    assert merged.task_spec["layer_cut_allowed"] is True


def test_llm_does_not_fill_unexpressed_fields():
    message = "切割3mm碳纤维"
    client = StaticTaskIntakeLLM([
        _llm_update("process_type", "cutting", "切割"),
        _llm_update("material", "CFRP", "碳纤维"),
        _llm_update("thickness_mm", 3, "3mm", unit="mm"),
    ])
    patch, merged = _pipeline(message, {}, _context(*(
        "material", "process_type", "thickness_mm", "quality_requirement",
        "cut_length_mm", "efficiency_requirement", "auxiliary", "layer_cut_allowed",
    )), client)
    assert {item.field_name for item in patch.updates} == {"material", "process_type", "thickness_mm"}
    assert "auxiliary" not in merged.task_spec
    assert "layer_cut_allowed" not in merged.task_spec
    assert "cut_length_mm" not in merged.task_spec


def test_strict_key_value_parser_is_explicit_and_bypasses_llm():
    class MustNotRun:
        provider = "test"

        def chat(self, *args, **kwargs):
            raise AssertionError("strict key=value input must not call LLM")

    message = "切割长度=100mm；轮廓=直线；辅助介质=压缩空气；允许分层切割=true"
    patch, merged = _pipeline(
        message,
        {"process_type": "cutting"},
        _context("cut_length_mm", "auxiliary", "layer_cut_allowed"),
        MustNotRun(),
    )
    assert patch.extraction_mode == "strict_key_value"
    assert merged.task_spec["cut_length_mm"] == 100
    assert merged.task_spec["contour_type"] == "straight"
    assert merged.task_spec["auxiliary"] == "compressed_air"
    assert merged.task_spec["layer_cut_allowed"] is True


def test_strict_key_value_parser_never_guesses_free_text():
    assert StrictKeyValueParser().parse("100mm直线", _context("cut_length_mm")) is None


def test_conflict_requires_explicit_correction_evidence():
    current = {"process_type": "cutting", "thickness_mm": 3}
    plain = StaticTaskIntakeLLM([_llm_update("thickness_mm", 5, "厚度5mm", unit="mm")])
    _, conflict = _pipeline("厚度5mm", current, _context(), plain)
    assert conflict.task_spec["thickness_mm"] == 3
    assert conflict.conflicts[0]["reason"] == "confirmed_value_requires_explicit_correction"

    corrected_client = StaticTaskIntakeLLM([
        _llm_update(
            "thickness_mm", 5, "刚才厚度说错了，改成5mm", unit="mm", operation="correct"
        )
    ])
    _, corrected = _pipeline(
        "刚才厚度说错了，改成5mm", current, _context(), corrected_client
    )
    assert corrected.task_spec["thickness_mm"] == 5
    assert corrected.revision_history[0]["old_value"] == 3


@pytest.mark.parametrize(("evidence", "reason"), [
    ("", "evidence_required"),
    ("不存在的100mm", "evidence_not_in_user_message"),
])
def test_missing_or_fabricated_evidence_is_rejected(evidence, reason):
    current = {"process_type": "cutting"}
    client = StaticTaskIntakeLLM([
        _llm_update("cut_length_mm", 100, evidence, unit="mm"),
    ])
    patch, merged = _pipeline("长度尚未确定", current, _context("cut_length_mm"), client)
    assert patch.updates == []
    assert patch.rejected_candidates[0]["reason"] == reason
    assert merged.task_spec == current


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
        extraction_source="llm_semantic_extraction",
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


def test_llm_failure_retries_once_then_preserves_state():
    class CountingTimeoutClient:
        provider = "test"
        model = "timeout-test"

        def __init__(self):
            self.calls = []

        def chat(self, *args, **kwargs):
            self.calls.append(kwargs)
            raise TimeoutError("timeout")

    client = CountingTimeoutClient()
    current = {"process_type": "cutting", "thickness_mm": 5}
    patch, merged = _pipeline(
        "边缘质量要尽可能干净", current, _context("quality_requirement"), client
    )
    assert len(client.calls) == 2
    assert "response_format" in client.calls[0]
    assert "response_format" not in client.calls[1]
    assert patch.attempt_count == 2
    assert patch.degraded is True
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


def test_parser_stall_stops_repeating_identical_question(isolated_root, monkeypatch):
    _equipment()
    llm = ScriptedTaskIntakeLLM()
    monkeypatch.setattr(
        "ultrafast_memory.process_workflow.chat_orchestrator.create_llm_client",
        lambda config: llm,
    )
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


def test_stream_and_non_stream_workflow_state_are_consistent(isolated_root, monkeypatch):
    _equipment()
    llm = ScriptedTaskIntakeLLM()
    monkeypatch.setattr(
        "ultrafast_memory.process_workflow.chat_orchestrator.create_llm_client",
        lambda config: llm,
    )
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
    assert "deterministic_extractor" not in source
    assert not (project_root / "src/ultrafast_agent/task_intake/deterministic_extractor.py").exists()
    assert not (project_root / "src/ultrafast_agent/task_intake/candidate_resolver.py").exists()
