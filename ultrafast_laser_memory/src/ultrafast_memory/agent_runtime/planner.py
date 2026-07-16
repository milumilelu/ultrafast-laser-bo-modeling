from __future__ import annotations

import json
from collections.abc import Callable
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ultrafast_memory.agent_runtime.actions import ACTION_SCHEMA_VERSION, AgentAction
from ultrafast_memory.agent_runtime.tool_registry import TOOL_REGISTRY_VERSION
from ultrafast_memory.core.time_utils import utc_now_iso


class PlannerActionError(ValueError):
    def __init__(self, code: str, *, location: str, received: Any, expected: Any):
        super().__init__(code)
        self.code = code
        self.location = location
        self.received = received
        self.expected = expected


class MainAgentPlanner:
    """Choose one Tool, question, or answer without a separate Skill action loop."""

    def __init__(self, client: Any):
        self.client = client
        self._model_call_sequence = 0
        self._last_prompt_section_chars: dict[str, int] = {}

    def decide(
        self,
        *,
        message: str,
        working_context: dict[str, Any],
        available_tools: list[dict[str, Any]] | None = None,
        active_skills: list[str] | None = None,
        recent_tool_results: list[dict[str, Any]] | None = None,
        skill_catalog: list[dict[str, Any]] | None = None,
        skill_guidance: list[dict[str, Any]] | None = None,
        recent_dialogue: list[dict[str, str]] | None = None,
        runtime_hints: dict[str, Any] | None = None,
        model_call_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentAction:
        tools = available_tools or []
        tool_names = [str(item["name"]) for item in tools]
        observations = recent_tool_results or []
        if self.client is None or getattr(self.client, "provider", None) == "mock":
            return self.deterministic_fallback(
                working_context, observations, tool_names,
                reason="main_agent_model_unavailable",
            )

        guidance = skill_guidance or []
        system_prompt = self._system_prompt()
        prompt = self._prompt(
            message, working_context, tools, guidance,
            observations, recent_dialogue or [], runtime_hints or {},
        )
        last_error: Exception | None = None
        last_raw_content = ""
        last_parsed_action: dict[str, Any] | None = None
        repair_allowed = bool((runtime_hints or {}).get("repair_allowed", True))
        max_attempts = 2 if repair_allowed else 1
        for attempt in range(1, max_attempts + 1):
            stage = "request"
            call_started = monotonic()
            response_chars = 0
            options: dict[str, Any] = {"temperature": 0, "timeout": 60}
            options["response_format"] = {"type": "json_object"}
            is_repair = attempt == 2
            call_system_prompt = (
                system_prompt if not is_repair
                else "你只修复一个 JSON Action。不得重新规划任务，不得输出解释或 Markdown。"
            )
            user_prompt = (
                prompt if not is_repair
                else self._repair_prompt(
                    last_raw_content,
                    last_parsed_action,
                    last_error,
                    tool_names,
                )
            )
            self._model_call_sequence += 1
            call_id = f"main-agent-{uuid4().hex}"
            common = {
                "call_id": call_id,
                "call_sequence": self._model_call_sequence,
                "provider": getattr(self.client, "provider", None),
                "model": getattr(self.client, "model", None),
                "component": "main_agent_planner",
                "purpose": "选择下一项 Tool、合并追问或最终答复",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "timeout_s": int(options["timeout"]),
                "prompt_chars": len(call_system_prompt) + len(user_prompt),
                "prompt_section_chars": dict(self._last_prompt_section_chars),
                "repair": is_repair,
                "action_schema_version": ACTION_SCHEMA_VERSION,
                "tool_registry_version": TOOL_REGISTRY_VERSION,
                "started_at": utc_now_iso(),
            }
            self._emit_model_event(model_call_sink, "model_call_started", {
                **common, "status_detail": "waiting_provider_response",
            })
            try:
                stage = "provider"
                result = self.client.chat([
                    {"role": "system", "content": call_system_prompt},
                    {"role": "user", "content": user_prompt},
                ], **options)
                provider_ms = (monotonic() - call_started) * 1000
                content = str(result.get("content") or "")
                last_raw_content = content
                response_chars = len(content)
                self._emit_model_event(model_call_sink, "model_provider_response_received", {
                    **common,
                    "duration_ms": round(provider_ms, 3),
                    "response_chars": response_chars,
                    "first_byte_available": False,
                    "timing_note": "同步 LLM 客户端仅能测量完整响应返回，不能可靠区分首字节。",
                    "completed_at": utc_now_iso(),
                })

                stage = "parse"
                parse_started = monotonic()
                try:
                    parsed = self._json(content)
                except (json.JSONDecodeError, TypeError):
                    if self._looks_like_natural_response(content):
                        parsed = {
                            "action": "respond",
                            "decision_summary": "Main LLM 直接生成自然语言回复。",
                            "message": content.strip(),
                        }
                    else:
                        raise
                raw = self._normalize_provider_action(parsed, message)
                last_parsed_action = raw
                parse_ms = (monotonic() - parse_started) * 1000
                self._emit_model_event(model_call_sink, "model_parse_completed", {
                    **common, "duration_ms": round(parse_ms, 3), "parse_success": True,
                    "response_chars": response_chars,
                })

                stage = "validation"
                validation_started = monotonic()
                action = self._validate_action(raw, tool_names)
                validation_ms = (monotonic() - validation_started) * 1000
                total_ms = (monotonic() - call_started) * 1000
                self._emit_model_event(model_call_sink, "model_validation_completed", {
                    **common,
                    "duration_ms": round(validation_ms, 3),
                    "validation_success": True,
                    "action": action.action,
                    "tool_name": action.tool_name,
                    "skills_used": action.skills_used,
                })
                self._emit_model_event(model_call_sink, "model_call_completed", {
                    **common, "duration_ms": round(total_ms, 3),
                    "response_chars": response_chars, "action": action.action,
                    "tool_name": action.tool_name, "completed_at": utc_now_iso(),
                })
                return action.model_copy(update={
                    "provider": result.get("provider") or getattr(self.client, "provider", None),
                    "model": result.get("model") or getattr(self.client, "model", None),
                })
            except Exception as exc:  # noqa: BLE001 - retried then sanitized
                last_error = exc
                errors = self._safe_error_details(exc)
                self._emit_model_event(model_call_sink, "model_call_failed", {
                    **common,
                    "failure_stage": stage,
                    "duration_ms": round((monotonic() - call_started) * 1000, 3),
                    "response_chars": response_chars,
                    "errors": errors,
                    "raw_model_output": self._safe_debug_value(last_raw_content),
                    "parsed_action": self._safe_debug_value(last_parsed_action),
                    "will_retry": attempt < max_attempts,
                    "completed_at": utc_now_iso(),
                })

        return self.deterministic_fallback(
            working_context,
            observations,
            tool_names,
            reason=f"planner_validation_failed:{type(last_error).__name__ if last_error else 'unknown'}",
            error_details=self._safe_error_details(last_error),
        )

    @staticmethod
    def deterministic_fallback(
        working_context: dict[str, Any],
        recent_tool_results: list[dict[str, Any]],
        available_tool_names: list[str],
        *,
        reason: str,
        error_details: list[dict[str, Any]] | None = None,
    ) -> AgentAction:
        task = dict(working_context.get("task") or {})
        pending = working_context.get("pending_user_action")
        common = {
            "provider": "deterministic_fallback",
            "model": "v31-safe-next-action",
            "error_details": error_details or [],
        }
        if pending:
            message = pending.get("message") if isinstance(pending, dict) else str(pending)
            return AgentAction(
                action="ask_user",
                decision_summary=f"Fallback：当前明确等待用户输入（{reason}）。",
                message=message or "请补充当前步骤所需的信息。",
                **common,
            )
        if task and not working_context.get("equipment_context") \
                and "get_equipment_context" in available_tool_names:
            return AgentAction(
                action="call_tool",
                decision_summary=f"Fallback：任务事实已保存，下一步读取设备上下文（{reason}）。",
                tool_name="get_equipment_context",
                arguments={},
                **common,
            )

        parameter_observation = MainAgentPlanner._latest_tool_observation(
            recent_tool_results, "recommend_process_parameters",
        )
        equipment = working_context.get("equipment_context") or {}
        if task and equipment and parameter_observation is None \
                and "recommend_process_parameters" in available_tool_names:
            process_plan = working_context.get("process_plan") or {}
            variables = [
                str(item.get("name"))
                for item in process_plan.get("controllable_variables") or []
                if isinstance(item, dict) and item.get("name")
            ]
            if not variables:
                variables = list((equipment.get("tunable_capabilities") or {}).keys())
            fallback_plan = process_plan or {
                "objective": "为当前任务生成保守的试切候选",
                "controllable_variables": [
                    {"name": name, "role": "process_setpoint"} for name in variables
                ],
            }
            return AgentAction(
                action="call_tool",
                decision_summary=f"Fallback：设备已读取，按统一参数策略继续（{reason}）。",
                tool_name="recommend_process_parameters",
                arguments={
                    "task_context": task,
                    "process_plan": fallback_plan,
                    "variables": variables,
                    "equipment_context": equipment,
                },
                **common,
            )
        if parameter_observation is not None:
            source = parameter_observation.get("selected_source") \
                or parameter_observation.get("source_type") or "未形成可用来源"
            allowed = parameter_observation.get("allowed_for_trial") is True
            equipment_ready = bool(equipment) \
                and equipment.get("active", True) is not False \
                and not equipment.get("missing_equipment_fields")
            if allowed:
                next_action = "选择简化试切或完整试切。"
            elif equipment_ready:
                next_action = "补充可审核证据或合格历史/实验数据。"
            else:
                next_action = "补全有效设备配置，并补充可审核证据或合格历史/实验数据。"
            return AgentAction(
                action="respond",
                decision_summary=f"Fallback：已有参数策略结果，返回当前阶段结论（{reason}）。",
                message=(
                    f"参数策略检查已完成，当前来源：{source}；"
                    f"试切权限：{'允许' if allowed else '未确认'}。"
                    f"这些结果不表示任务完成。NextAction：{next_action}"
                ),
                **common,
            )
        return AgentAction(
            action="respond",
            decision_summary=f"Fallback：返回已确认事实和安全下一步（{reason}）。",
            message=(
                "已保存当前明确任务事实，但暂时无法可靠生成下一项结构化行动。"
                "本次回复不表示任务完成。NextAction：补充新的任务事实或稍后重试。"
            ),
            **common,
        )

    @staticmethod
    def _latest_tool_observation(
        observations: list[dict[str, Any]], tool_name: str,
    ) -> dict[str, Any] | None:
        for item in reversed(observations):
            if item.get("tool_name") == tool_name:
                data = item.get("data")
                return data if isinstance(data, dict) else item
            meta = item.get("meta") if isinstance(item, dict) else None
            if isinstance(meta, dict) and meta.get("tool_name") == tool_name:
                data = item.get("data")
                return data if isinstance(data, dict) else item
        return None

    @staticmethod
    def _emit_model_event(
        sink: Callable[[dict[str, Any]], None] | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if sink is None:
            return
        try:
            sink({"event_type": event_type, **payload})
        except Exception:  # noqa: BLE001 - observability cannot block planning
            return

    @staticmethod
    def _validate_action(
        raw: dict[str, Any],
        available_tool_names: list[str],
        *_compatibility_args: Any,
    ) -> AgentAction:
        action = AgentAction.model_validate(raw)
        if action.action == "call_tool" and action.tool_name not in available_tool_names:
            raise PlannerActionError(
                "tool_not_registered",
                location="tool_name",
                received=action.tool_name,
                expected=available_tool_names,
            )
        return action

    @staticmethod
    def _normalize_provider_action(raw: dict[str, Any], user_message: str) -> dict[str, Any]:
        if isinstance(raw.get("actions"), list):
            actions = raw["actions"]
            if not actions or not isinstance(actions[0], dict):
                raise ValueError("actions_must_contain_an_action_object")
            raw = dict(actions[0])
        else:
            raw = dict(raw)
        aliases = {
            "tool_call": "call_tool", "clarify": "ask_user",
            "request_clarification": "ask_user", "answer": "respond",
            "final_answer": "respond", "continue_planning": "update_context",
        }
        raw["action"] = aliases.get(str(raw.get("action") or raw.get("type") or ""), raw.get("action"))
        raw.setdefault("tool_name", raw.get("tool"))
        if raw.get("arguments") is None:
            raw["arguments"] = raw.get("args") or {}
        else:
            raw.setdefault("arguments", raw.get("args") or {})
        if raw.get("context_updates") is None:
            raw["context_updates"] = {}
        else:
            raw.setdefault("context_updates", {})
        if isinstance(raw.get("context_updates"), dict):
            raw["context_updates"] = MainAgentPlanner._normalize_context_updates(
                raw["context_updates"]
            )
        raw.setdefault("message", raw.get("answer") or raw.get("content"))
        raw.setdefault("decision_summary", str(raw.get("reason") or "执行主 Agent 选择的下一动作。"))
        skills_used = raw.get("skills_used")
        if skills_used is None and raw.get("skill"):
            raw["skills_used"] = [raw["skill"]]
        raw.setdefault("skills_used", [])
        return raw

    @staticmethod
    def _normalize_context_updates(updates: dict[str, Any]) -> dict[str, Any]:
        """Normalize wire paths structurally without interpreting task semantics."""
        normalized: dict[str, Any] = {}
        context_roots = {
            "task", "process_plan", "trial_plan",
        }
        tool_owned_roots = {
            "task_intake", "equipment_context", "documents", "observations",
            "pending_user_action", "active_skills",
        }

        def merge(target: dict[str, Any], value: dict[str, Any]) -> None:
            for key, item in value.items():
                if isinstance(target.get(key), dict) and isinstance(item, dict):
                    merge(target[key], item)
                else:
                    target[key] = item

        def set_path(target: dict[str, Any], parts: list[str], value: Any) -> None:
            cursor = target
            for part in parts[:-1]:
                child = cursor.get(part)
                if not isinstance(child, dict):
                    child = {}
                    cursor[part] = child
                cursor = child
            final = parts[-1]
            if isinstance(cursor.get(final), dict) and isinstance(value, dict):
                merge(cursor[final], value)
            else:
                cursor[final] = value

        for key, value in updates.items():
            parts = [part for part in str(key).split(".") if part]
            if not parts:
                continue
            if parts[0] in tool_owned_roots:
                continue
            if parts[0] not in context_roots:
                parts.insert(0, "task")
            set_path(normalized, parts, value)
        return normalized

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
    def _looks_like_natural_response(content: str) -> bool:
        text = content.strip()
        return bool(text) and not text.startswith(("{", "[", "```"))

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是超快激光加工前台唯一主 Agent。每次只返回一个 JSON 对象，不输出 Markdown。"
            "字段仅包括 action,decision_summary,skills_used,tool_name,arguments,message,context_updates。"
            "action 仅限 update_context、call_tool、ask_user、respond；Skill 不是行动，不得加载或卸载 Skill。"
            "Skill 只提供提示和流程指导：不授予权限、不隐藏 Tool、不校验行动、不写入事实，"
            "也不得阻塞 Main LLM 的任务理解与自然对话。"
            "update_context 只更新事实并继续规划；respond 只结束当前对话轮次，不表示加工任务完成。"
            "你是任务语义的唯一裁决者：直接理解完整用户原话和会话上下文；规则、路由提示、Task Intake、"
            "检索和工具都无权替你判定材料、几何、工艺意图、缺失项或用户修正。"
            "当前用户原话的语义优先于旧 Working Context；若用户提供了新事实或纠正，直接用"
            "context_updates.task 的嵌套对象更新规范任务，不要求用户使用‘修正’等关键词。"
            "context_updates 只可写 task、process_plan、trial_plan；设备、Observation、文档、Skill 状态和待确认状态由运行时或 Tool 维护。"
            "recent_dialogue 用于解析‘同意’‘不是’‘继续’等承接上一轮的短回复；不得脱离上一轮问题猜测其授权范围。"
            "不得把 task 字段写成 geometry.feature_type 之类的顶层点号键。"
            "一次读取用户消息、Working Context、相关 Observation、注入的 Skill 指导和 Tool Schema。"
            "Tool 是外部能力；需要证据、设备事实、参数计算或执行时选择一个 Tool，Tool 返回后再决策。"
            "任何新增能力失败、缺证或返回低质量结果，都只能成为 Observation，不能阻止你理解任务、"
            "正常追问或自然回复；只有真实安全边界和本任务不可缺少的信息才可阻塞执行。"
            "relevant_observations 已是去重后的公开摘要或 Evidence Pack；正文省略不代表需要重复检索。"
            "若 evidence_quality 显示 degraded 或 candidate_only，不得因 evidence_status=sufficient 就当作"
            "直接匹配的参数证据。"
            "同一行动可以提交明确的 context_updates；不得逐字段写状态，也不得重复查询相同 Tool。"
            "只有缺失信息会实质改变加工路线且无法安全假设时才 ask_user；按阻塞信息量提出 1 至 5 个问题，"
            "只有一个阻塞字段时只问一个，不得为凑数量询问非阻塞偏好。"
            "不得询问应由系统规划的功率、频率、速度等参数。"
            "方案结构、工艺变量和评价指标必须按当前任务动态选择，不套用通孔、切割或其他案例模板。"
            "参数必须区分设备固定条件、设备可调能力、工艺设定值、策略参数和派生指标。"
            "设备范围只是边界，不能用范围中点冒充推荐；不得改写 Tool 返回的证据和 provenance。"
            "所有参数推荐只能调用 recommend_process_parameters；该 Tool 内部强制 BO→审核 RAG 顺序，"
            "不得请求或伪造其内部子步骤。"
            "参数 Tool 返回 insufficient_data 时，不得把自行编造的数值直接交给 manage_trial。"
            "BO 与审核 RAG 均不足时不得生成任何数值候选；说明证据缺口并继续自然回复。"
            "加工任务信息足够时继续调用必要 Tool，并用 respond 返回当前阶段结论和明确 NextAction。"
            "真实设备动作仍须遵守 Tool 的安全边界和当次用户授权。"
        )

    def _prompt(
        self,
        message: str,
        working_context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        skill_guidance: list[dict[str, Any]],
        recent_tool_results: list[dict[str, Any]],
        recent_dialogue: list[dict[str, str]],
        runtime_hints: dict[str, Any],
    ) -> str:
        wire_example = {
            "action": "call_tool",
            "decision_summary": "先检索与当前材料和加工目标匹配的内部证据。",
            "skills_used": ["evidence_research", "process_planning"],
            "tool_name": "search_knowledge",
            "arguments": {"query": "当前任务的检索问题"},
            "message": None,
            "context_updates": {},
        }
        sections = [
            ("wire_example", wire_example),
            ("recent_dialogue", recent_dialogue),
            ("user_message", message),
            ("working_context", working_context),
            ("relevant_observations", recent_tool_results),
            ("injected_skill_guidance", skill_guidance),
            ("available_tools", available_tools),
            ("runtime_hints", runtime_hints),
        ]
        encoded = [
            (name, json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str))
            for name, value in sections
        ]
        self._last_prompt_section_chars = {name: len(value) for name, value in encoded}
        return "\n".join(f"{name}={value}" for name, value in encoded)

    @classmethod
    def _repair_prompt(
        cls,
        raw_output: str,
        parsed_action: dict[str, Any] | None,
        exc: Exception | None,
        allowed_tools: list[str],
    ) -> str:
        payload = {
            "task": "只修复下面的 Action JSON，不重新规划任务。",
            "raw_action": cls._safe_debug_value(raw_output),
            "parsed_action": cls._safe_debug_value(parsed_action),
            "validation_errors": cls._safe_error_details(exc),
            "action_schema_version": ACTION_SCHEMA_VERSION,
            "allowed_actions": ["update_context", "call_tool", "ask_user", "respond"],
            "required_types": {
                "decision_summary": "string",
                "arguments": "object",
                "context_updates": "object",
                "skills_used": "array[string]",
            },
            "allowed_tools": allowed_tools,
            "tool_registry_version": TOOL_REGISTRY_VERSION,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _safe_error_details(exc: Exception | None) -> list[dict[str, Any]]:
        if isinstance(exc, ValidationError):
            return [
                {
                    "loc": ".".join(map(str, item.get("loc") or [])),
                    "type": str(item.get("type") or ""),
                    "msg": str(item.get("msg") or ""),
                    "received": MainAgentPlanner._safe_debug_value(item.get("input")),
                    "expected": MainAgentPlanner._expected_for_error(item),
                }
                for item in exc.errors()
            ]
        if isinstance(exc, PlannerActionError):
            return [{
                "loc": exc.location,
                "type": exc.code,
                "msg": str(exc),
                "received": MainAgentPlanner._safe_debug_value(exc.received),
                "expected": MainAgentPlanner._safe_debug_value(exc.expected),
            }]
        if exc is None:
            return []
        return [{
            "loc": "",
            "type": type(exc).__name__,
            "msg": str(exc)[:240],
            "received": None,
            "expected": None,
        }]

    @staticmethod
    def _expected_for_error(item: dict[str, Any]) -> Any:
        expected = {
            "dict_type": "object",
            "list_type": "array",
            "string_type": "string",
            "literal_error": item.get("ctx", {}).get("expected"),
            "missing": "required field",
            "value_error": item.get("ctx", {}).get("error"),
        }
        return MainAgentPlanner._safe_debug_value(expected.get(str(item.get("type") or "")))

    @staticmethod
    def _safe_debug_value(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:2000]
        if isinstance(value, list):
            return [MainAgentPlanner._safe_debug_value(item) for item in value[:20]]
        if isinstance(value, dict):
            blocked = {"api_key", "authorization", "password", "secret", "token"}
            return {
                str(key): "[REDACTED]" if str(key).lower() in blocked
                else MainAgentPlanner._safe_debug_value(item)
                for key, item in list(value.items())[:40]
            }
        return str(value)[:500]
