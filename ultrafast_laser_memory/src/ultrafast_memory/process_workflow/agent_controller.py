from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from ultrafast_agent.task_intake.strict_key_value_parser import StrictKeyValueParser
from ultrafast_agent.task_intake.schemas import ClarificationContext


class AgentAction(BaseModel):
    action: Literal["call_tool", "ask_user", "direct_answer"]
    decision_summary: str
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    provider: str | None = None
    model: str | None = None


class ProcessAgentController:
    """Main-LLM action selector; it cannot mutate domain state directly."""

    def __init__(self, client: Any):
        self.client = client

    def decide(
        self,
        *,
        message: str,
        task_spec: dict[str, Any],
        business_state: str,
        context: ClarificationContext,
        allowed_actions: list[str],
        campaign: dict[str, Any] | None = None,
        recent_tool_results: list[dict[str, Any]] | None = None,
    ) -> AgentAction:
        explicit = StrictKeyValueParser().parse(message, context)
        if explicit is not None:
            return AgentAction(
                action="call_tool",
                decision_summary="用户提供了显式字段赋值，调用状态写入工具校验并提交。",
                tool_name="update_task_spec",
                arguments={"updates": [
                    {
                        "field_name": item.field_name,
                        "value": item.raw_value,
                        "unit": item.unit,
                        "evidence": item.evidence,
                        "operation": item.operation,
                    }
                    for item in explicit.updates
                ]},
                provider="deterministic_explicit_input",
                model="strict-key-value-adapter",
            )
        if self.client is None or getattr(self.client, "provider", None) == "mock":
            return AgentAction(
                action="ask_user",
                decision_summary="主 Agent LLM 当前不可用，不能可靠解释自由文本并写入状态。",
                message="当前无法可靠理解并提交这条自然语言信息，请稍后重试。现有任务状态未被修改。",
                provider=getattr(self.client, "provider", None),
                model=getattr(self.client, "model", None),
            )
        prompt = self._prompt(
            message, task_spec, business_state, context, allowed_actions,
            campaign or {}, recent_tool_results or [],
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                options: dict[str, Any] = {"temperature": 0, "timeout": 25}
                if attempt == 0:
                    options["response_format"] = self._response_format()
                result = self.client.chat([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ], **options)
                raw = self._json(result.get("content") or "")
                action = self._validate_action(raw, allowed_actions)
                return action.model_copy(update={
                    "provider": result.get("provider") or getattr(self.client, "provider", None),
                    "model": result.get("model") or getattr(self.client, "model", None),
                })
            except Exception as exc:  # noqa: BLE001 - converted into a safe Agent action
                last_error = exc
        return AgentAction(
            action="ask_user",
            decision_summary=f"主 Agent 行动规划失败：{type(last_error).__name__ if last_error else 'unknown'}。",
            message="我暂时无法安全处理这条任务更新，现有状态未被修改。请稍后重试。",
            provider=getattr(self.client, "provider", None),
            model=getattr(self.client, "model", None),
        )

    @staticmethod
    def _validate_action(raw: dict[str, Any], allowed_actions: list[str]) -> AgentAction:
        # Read compatibility for scripted fixtures produced by the retired field extractor.
        if "updates" in raw and "action" not in raw:
            raw = {
                "action": "call_tool",
                "decision_summary": "用户提供了任务信息，调用 update_task_spec 校验并提交。",
                "tool_name": "update_task_spec",
                "arguments": {"updates": raw.get("updates") or []},
            }
        action = AgentAction.model_validate(raw)
        selected = action.tool_name if action.action == "call_tool" else action.action
        if selected not in allowed_actions:
            raise ValueError(f"action_not_allowed:{selected}")
        if action.action == "call_tool" and action.tool_name != "update_task_spec":
            raise ValueError("unsupported_tool")
        return action

    @staticmethod
    def _json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise TypeError("Agent action must be a JSON object")
        return value

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是超快激光加工主 Agent。你负责理解上下文、规划下一动作和选择工具。"
            "用户明确提供或修正任务信息时调用 update_task_spec；不得直接声称状态已修改。"
            "不得自行生成 BO 最优参数，不得绕过设备边界、数据准入、知识审核或人工批准。"
            "不得因为用户未使用固定格式而拒绝理解自然语言。只返回符合 Schema 的行动 JSON。"
        )

    @staticmethod
    def _prompt(
        message: str,
        task_spec: dict[str, Any],
        business_state: str,
        context: ClarificationContext,
        allowed_actions: list[str],
        campaign: dict[str, Any],
        recent_tool_results: list[dict[str, Any]],
    ) -> str:
        return (
            f"user_message={json.dumps(message, ensure_ascii=False)}\n"
            f"task_spec={json.dumps(task_spec, ensure_ascii=False)}\n"
            f"business_state={business_state}\n"
            f"missing_fields={json.dumps(context.pending_fields, ensure_ascii=False)}\n"
            f"previous_questions={json.dumps(context.previous_questions, ensure_ascii=False)}\n"
            f"expected_answer_types={json.dumps(context.expected_answer_types, ensure_ascii=False)}\n"
            f"trial_campaign={json.dumps(campaign, ensure_ascii=False)}\n"
            f"recent_tool_results={json.dumps(recent_tool_results[-3:], ensure_ascii=False)}\n"
            f"allowed_actions={json.dumps(allowed_actions, ensure_ascii=False)}"
        )

    @staticmethod
    def _response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_action",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["action", "decision_summary", "tool_name", "arguments", "message"],
                    "properties": {
                        "action": {"type": "string", "enum": ["call_tool", "ask_user", "direct_answer"]},
                        "decision_summary": {"type": "string"},
                        "tool_name": {"type": ["string", "null"]},
                        "arguments": {"type": "object"},
                        "message": {"type": ["string", "null"]},
                    },
                },
            },
        }
