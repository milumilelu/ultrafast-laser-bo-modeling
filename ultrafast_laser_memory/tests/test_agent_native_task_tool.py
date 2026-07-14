from __future__ import annotations

from fastapi.testclient import TestClient

from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_agent.task_intake.update_task_spec_tool import update_task_spec
from ultrafast_agent.runtime import ToolContract, ToolExecutor, ToolRegistry
from ultrafast_memory.apps.api.main import app
from ultrafast_memory.chat.session_state import get_session_state
from ultrafast_memory.process_workflow.business_state import BusinessState, allowed_agent_actions
from ultrafast_memory.process_workflow.agent_controller import ProcessAgentController


def _context(*pending: str) -> ClarificationContext:
    return ClarificationContext(
        workflow_type="complex_process_task",
        stage="REQUIREMENTS_PENDING",
        pending_fields=list(pending),
        ordered_fields=list(pending),
    )


def test_update_task_spec_tool_rejects_invalid_unit_without_state_pollution(isolated_root) -> None:
    client = TestClient(app)
    session_id = client.post("/chat/sessions", json={}).json()["session_id"]
    context = _context("cut_length_mm")

    result = update_task_spec(
        {"updates": [{
            "field_name": "cut_length_mm",
            "value": 100,
            "unit": "meter",
            "evidence": "100 meter",
        }]},
        {
            "session_id": session_id,
            "message_id": "msg-invalid-unit",
            "user_message": "100 meter",
            "clarification_context": context.model_dump(mode="json"),
        },
    )

    assert result["status"] == "partial"
    assert result["applied"] == []
    assert result["rejected"][0]["reason"] == "normalization_failed:ValueError"
    assert get_session_state(session_id)["collected_slots"]["process_task_spec"] == {}


def test_business_state_exposes_permissions_instead_of_parser_status() -> None:
    intake = allowed_agent_actions(BusinessState.INTAKE)
    optimization = allowed_agent_actions(BusinessState.OPTIMIZATION)

    assert "update_task_spec" in intake
    assert "run_bo_recommendation" not in intake
    assert "run_bo_recommendation" in optimization
    assert "update_task_spec" not in optimization
    assert "production_approve" not in optimization


def test_tool_executor_enforces_human_approval_and_prohibition() -> None:
    registry = ToolRegistry()
    registry.register(ToolContract(
        name="approve_dataset",
        purpose="high risk test",
        handler=lambda payload, context: {"status": "success"},
        permission_level=3,
        requires_human_approval=True,
    ))
    registry.register(ToolContract(
        name="control_machine",
        purpose="prohibited test",
        handler=lambda payload, context: {"status": "success"},
        permission_level=4,
        prohibited=True,
    ))
    executor = ToolExecutor(registry)

    blocked = executor.execute("approve_dataset", {}, {})
    approved = executor.execute("approve_dataset", {}, {"human_approved": True})
    prohibited = executor.execute("control_machine", {}, {"human_approved": True})

    assert blocked.error_code == "human_approval_required"
    assert approved.status == "succeeded"
    assert prohibited.error_code == "tool_prohibited"


def test_main_agent_native_action_selects_update_tool() -> None:
    class NativeActionLLM:
        provider = "deepseek"
        model = "deepseek-v4-flash"

        def chat(self, messages, **kwargs):
            return {
                "provider": self.provider,
                "model": self.model,
                "content": (
                    '{"action":"call_tool","decision_summary":"提交用户明确字段",'
                    '"tool_name":"update_task_spec","arguments":{"updates":[{'
                    '"field_name":"cut_length_mm","value":100,"unit":"mm",'
                    '"evidence":"100mm"}]},"message":null}'
                ),
            }

    action = ProcessAgentController(NativeActionLLM()).decide(
        message="长度100mm",
        task_spec={"process_type": "cutting"},
        business_state="INTAKE",
        context=_context("cut_length_mm"),
        allowed_actions=allowed_agent_actions(BusinessState.INTAKE),
    )

    assert action.action == "call_tool"
    assert action.tool_name == "update_task_spec"
    assert action.arguments["updates"][0]["value"] == 100
    assert action.provider == "deepseek"
