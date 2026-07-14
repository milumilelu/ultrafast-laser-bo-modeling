from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from ultrafast_agent.task_intake.schemas import ClarificationContext
from ultrafast_agent.task_intake.strict_key_value_parser import StrictKeyValueParser
from ultrafast_memory.agent_runtime.actions import AgentAction
from ultrafast_memory.llm.openai_compatible import LLMProviderError


class MainAgentPlanner:
    """Select exactly one next action; domain mutation remains tool-owned."""

    def __init__(self, client: Any):
        self.client = client

    def decide(
        self,
        *,
        message: str,
        task_spec: dict[str, Any],
        business_state: str,
        context: ClarificationContext,
        available_tools: list[dict[str, Any]] | None = None,
        active_skills: list[str] | None = None,
        campaign: dict[str, Any] | None = None,
        recent_tool_results: list[dict[str, Any]] | None = None,
        skill_catalog: list[dict[str, Any]] | None = None,
    ) -> AgentAction:
        explicit = StrictKeyValueParser().parse(message, context)
        if explicit is not None:
            return AgentAction(
                action="call_tool",
                decision_summary="用户提供了显式字段赋值，调用状态写入工具校验并提交。",
                tool_name="update_task_context",
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

        tools = available_tools or []
        catalog = skill_catalog or []
        prompt = self._prompt(
            message, task_spec, business_state, context, tools,
            active_skills or [], campaign or {}, recent_tool_results or [], catalog,
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                options: dict[str, Any] = {"temperature": 0, "timeout": 25}
                if attempt == 0:
                    options["response_format"] = {"type": "json_object"}
                repair_note = ""
                if attempt and last_error is not None:
                    repair_note = "\n" + self._repair_note(last_error)
                result = self.client.chat([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt + repair_note},
                ], **options)
                raw = self._normalize_provider_action(self._json(result.get("content") or ""), message)
                action = self._validate_action(
                    raw,
                    [item["name"] for item in tools],
                    [item["name"] for item in catalog],
                )
                return action.model_copy(update={
                    "provider": result.get("provider") or getattr(self.client, "provider", None),
                    "model": result.get("model") or getattr(self.client, "model", None),
                })
            except Exception as exc:  # noqa: BLE001 - converted into a safe public Agent action
                last_error = exc

        details = self._safe_error_details(last_error)
        return AgentAction(
            action="ask_user",
            decision_summary=f"主 Agent 行动规划失败：{type(last_error).__name__ if last_error else 'unknown'}。",
            message="我暂时无法安全处理这条任务更新，现有状态未被修改。请稍后重试。",
            provider=getattr(self.client, "provider", None),
            model=getattr(self.client, "model", None),
            error_details=details,
        )

    @staticmethod
    def _validate_action(raw: dict[str, Any], available_tool_names: list[str], skill_names: list[str]) -> AgentAction:
        if "updates" in raw and not raw.get("action"):
            updates = raw.get("updates") or []
            raw = ({
                "action": "call_tool",
                "decision_summary": "用户提供了任务信息，调用 update_task_context 校验并提交。",
                "tool_name": "update_task_context",
                "arguments": {"updates": updates},
            } if updates else {
                "action": "ask_user",
                "decision_summary": "当前输出未识别出可验证的任务事实。",
                "message": "我还不能从这条信息中确认可写入的任务事实，请补充具体材料、加工动作或尺寸。",
            })
        if raw.get("action") == "direct_answer":
            raw["action"] = "final_answer"
        legacy_tools = {
            "update_task_spec": "update_task_context",
            "get_equipment_profile": "get_equipment_context",
            "search_rag": "search_knowledge",
            "run_bo_recommendation": "recommend_parameters_bo",
        }
        if raw.get("action") == "call_tool" and raw.get("tool_name") in legacy_tools:
            raw["tool_name"] = legacy_tools[raw["tool_name"]]
        action = AgentAction.model_validate(raw)
        if action.action == "call_tool":
            if not action.tool_name:
                raise ValueError("tool_name_required")
            if action.tool_name not in available_tool_names:
                raise ValueError(f"tool_not_registered:{action.tool_name}")
        elif action.action in {"load_skill", "unload_skill"}:
            if not action.skill_name or action.skill_name not in skill_names:
                raise ValueError(f"skill_not_registered:{action.skill_name}")
        elif not action.message:
            raise ValueError("message_required")
        return action

    @classmethod
    def _normalize_provider_action(cls, raw: dict[str, Any], user_message: str) -> dict[str, Any]:
        # Some OpenAI-compatible providers return a batch even when one action was requested.
        # Execute only the first action; the loop re-plans after each observation.
        if isinstance(raw.get("actions"), list):
            actions = raw["actions"]
            if not actions or not isinstance(actions[0], dict):
                raise ValueError("actions_must_contain_an_action_object")
            raw = dict(actions[0])
        else:
            raw = dict(raw)

        action_aliases = {
            "tool_call": "call_tool",
            "call_tool": "call_tool",
            "load_skill": "load_skill",
            "unload_skill": "unload_skill",
            "clarify": "ask_user",
            "request_clarification": "ask_user",
            "answer": "final_answer",
            "direct_answer": "final_answer",
        }
        raw["action"] = action_aliases.get(str(raw.get("action") or raw.get("type") or ""), raw.get("action"))
        if "tool_name" not in raw and raw.get("tool") is not None:
            raw["tool_name"] = raw.get("tool")
        if "skill_name" not in raw and raw.get("skill") is not None:
            raw["skill_name"] = raw.get("skill")
        if "arguments" not in raw:
            raw["arguments"] = raw.get("args") or {}
        if "message" not in raw:
            raw["message"] = raw.get("answer") or raw.get("content")
        raw.setdefault("decision_summary", str(raw.get("reason") or "执行主 Agent 选择的下一动作。"))

        if raw.get("action") == "call_tool" and raw.get("tool_name") in {"update_task_context", "update_task_spec"}:
            arguments = dict(raw.get("arguments") or {})
            updates = arguments.get("updates")
            if isinstance(updates, dict):
                arguments["updates"] = cls._updates_from_mapping(updates, user_message)
            elif isinstance(updates, list):
                arguments["updates"] = cls._normalize_update_list(updates, user_message)
            raw["arguments"] = arguments
        return raw

    @staticmethod
    def _normalize_update_list(updates: list[Any], user_message: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in updates:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            field = str(normalized.get("field_name") or "")
            value = normalized.get("value", normalized.get("raw_value"))
            normalized["value"] = value
            evidence = str(normalized.get("evidence") or "")
            if not evidence or evidence not in user_message:
                evidence = MainAgentPlanner._literal_evidence(field, value, user_message)
            normalized["evidence"] = evidence
            if field.endswith("_mm") and not normalized.get("unit"):
                normalized["unit"] = "mm" if re.search(r"(?:mm|毫米)", evidence, re.I) else None
            result.append(normalized)
        return result

    @staticmethod
    def _literal_evidence(field: str, value: Any, user_message: str) -> str:
        text = str(value)
        if field.endswith("_mm"):
            number = re.escape(text.strip()) if text.strip() else r"\d+(?:\.\d+)?"
            match = re.search(rf"{number}\s*(?:mm|毫米|cm|厘米|um|μm|µm)", user_message, re.I)
            return match.group(0) if match else (text if text and text in user_message else "")
        if field == "process_type":
            return next((marker for marker in ("切割", "通孔", "钻孔", "打孔", "刻蚀") if marker in user_message), "")
        if field == "material":
            return next((marker for marker in ("碳纤维复合板", "碳纤维复合材料", "碳纤维", "金刚石") if marker in user_message), "")
        return text if text and text in user_message else ""

    @staticmethod
    def _updates_from_mapping(updates: dict[str, Any], user_message: str) -> list[dict[str, Any]]:
        field_aliases = {
            "material": "material",
            "thickness": "thickness_mm",
            "thickness_mm": "thickness_mm",
            "process": "process_type",
            "process_type": "process_type",
            "objective": "objective",
            "quality": "quality_requirement",
        }
        result = []
        for source, value in updates.items():
            field = field_aliases.get(str(source))
            if not field:
                continue
            evidence = str(value)
            if evidence not in user_message and field == "process_type":
                evidence = next((marker for marker in ("切割", "通孔", "钻孔", "打孔", "刻蚀") if marker in user_message), "")
            unit = "mm" if field.endswith("_mm") and re.search(r"(?:mm|毫米)", str(value), re.I) else None
            result.append({"field_name": field, "value": value, "unit": unit, "evidence": evidence})
        if not any(item["field_name"] == "process_type" for item in result):
            marker = next((item for item in ("切割", "通孔", "钻孔", "打孔", "刻蚀") if item in user_message), None)
            if marker:
                result.append({"field_name": "process_type", "value": marker, "unit": None, "evidence": marker})
        return result

    @staticmethod
    def _json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise
            value = json.loads(text[start:end + 1])
        if not isinstance(value, dict):
            raise TypeError("Agent action must be a JSON object")
        return value

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是超快激光加工主 Agent。每次只规划一个下一动作，主循环会在动作产生观察后再次调用你。"
            "只返回一个 JSON 对象，禁止返回 actions 数组、Markdown 或多个动作。"
            "唯一字段协议：action, decision_summary, skill_name, tool_name, arguments, message。"
            "action 只能是 load_skill、unload_skill、call_tool、ask_user、final_answer。"
            "用户明确提供或修正任务事实时，先调用 update_task_context；updates 必须是数组，"
            "每项使用 field_name、value、unit、evidence。自然语言中的加工动词也应写入 process_type。"
            "不得直接声称状态已修改。Skill 只是可选专业指导，不是流程状态机。"
            "初始只暴露基础工具；需要专业能力时先 load_skill。TaskSpec 渐进补充，"
            "只在下一工具确实需要时询问缺失字段。不得生成无证据的参数，不得绕过设备边界、"
            "数据准入、知识审核或人工批准。不得因为用户未使用固定格式而拒绝理解自然语言。"
        )

    @staticmethod
    def _prompt(
        message: str,
        task_spec: dict[str, Any],
        business_state: str,
        context: ClarificationContext,
        available_tools: list[dict[str, Any]],
        active_skills: list[str],
        campaign: dict[str, Any],
        recent_tool_results: list[dict[str, Any]],
        skill_catalog: list[dict[str, Any]],
    ) -> str:
        return (
            'wire_example={"action":"call_tool","decision_summary":"保存明确任务事实",'
            '"skill_name":null,"tool_name":"update_task_context","arguments":{"updates":['
            '{"field_name":"material","value":"碳纤维复合板","unit":null,"evidence":"碳纤维复合板"},'
            '{"field_name":"thickness_mm","value":"2mm","unit":"mm","evidence":"2mm"},'
            '{"field_name":"process_type","value":"切割","unit":null,"evidence":"切割"}]},"message":null}\n'
            f"user_message={json.dumps(message, ensure_ascii=False)}\n"
            f"task_spec={json.dumps(task_spec, ensure_ascii=False)}\n"
            f"business_state={business_state}\n"
            f"missing_fields={json.dumps(context.pending_fields, ensure_ascii=False)}\n"
            f"previous_questions={json.dumps(context.previous_questions, ensure_ascii=False)}\n"
            f"expected_answer_types={json.dumps(context.expected_answer_types, ensure_ascii=False)}\n"
            f"trial_campaign={json.dumps(campaign, ensure_ascii=False)}\n"
            f"recent_tool_results={json.dumps(recent_tool_results[-3:], ensure_ascii=False)}\n"
            f"active_skills={json.dumps(active_skills, ensure_ascii=False)}\n"
            f"skill_catalog={json.dumps(skill_catalog, ensure_ascii=False)}\n"
            f"available_tools={json.dumps(available_tools, ensure_ascii=False)}"
        )

    @classmethod
    def _repair_note(cls, exc: Exception) -> str:
        details = cls._safe_error_details(exc)
        return (
            f"previous_output_errors={json.dumps(details, ensure_ascii=False)}\n"
            "修复要求：只返回一个行动 JSON 对象；不要 actions 数组；使用 action/tool_name/skill_name；"
            "call_tool.arguments.updates 必须是对象数组。"
        )

    @staticmethod
    def _safe_error_details(exc: Exception | None) -> list[dict[str, str]]:
        if exc is None:
            return []
        if isinstance(exc, ValidationError):
            return [
                {
                    "loc": ".".join(str(part) for part in item.get("loc") or ("action",)),
                    "type": str(item.get("type") or "validation_error"),
                    "msg": str(item.get("msg") or "invalid action")[:240],
                }
                for item in exc.errors(include_url=False, include_context=False)
            ]
        if isinstance(exc, LLMProviderError):
            code = exc.error_code or (f"http_{exc.status_code}" if exc.status_code else "provider_error")
            return [{"loc": "provider", "type": code, "msg": str(exc)[:240]}]
        return [{"loc": "planner", "type": type(exc).__name__, "msg": str(exc)[:240]}]


# Transitional Python name only. Runtime identity and normal imports use MainAgentPlanner.
ProcessAgentController = MainAgentPlanner
