from __future__ import annotations

import json
import re
from collections.abc import Callable
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ultrafast_domain.process import ProcessPlan
from ultrafast_domain.trial import TrialPlan
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
        skill_names = [str(item.get("name")) for item in guidance if item.get("name")]
        if not skill_names:
            skill_names = list(active_skills or [])
        system_prompt = self._system_prompt()
        prompt = self._prompt(
            message, working_context, tools, guidance,
            observations, runtime_hints or {},
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
                raw = self._normalize_provider_action(self._json(content), message)
                raw = self._protect_established_task_facts(raw, working_context, message)
                last_parsed_action = raw
                parse_ms = (monotonic() - parse_started) * 1000
                self._emit_model_event(model_call_sink, "model_parse_completed", {
                    **common, "duration_ms": round(parse_ms, 3), "parse_success": True,
                    "response_chars": response_chars,
                })

                stage = "validation"
                validation_started = monotonic()
                action = self._validate_action(raw, tool_names)
                allowed_skills = [name for name in action.skills_used if name in skill_names]
                if allowed_skills != action.skills_used:
                    action = action.model_copy(update={"skills_used": allowed_skills})
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
        intake = working_context.get("task_intake") or {}
        blocking = list(intake.get("blocking_fields") or [])
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
        if blocking:
            questions = {
                "geometry.depth_mm": "目标槽深是多少，还是要求贯穿？",
            }
            message = "\n".join(questions.get(field, f"请补充 {field}。") for field in blocking[:5])
            return AgentAction(
                action="ask_user",
                decision_summary=f"Fallback：只询问当前阻塞字段（{reason}）。",
                message=message,
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
                    "allow_llm_fallback": False,
                },
                **common,
            )
        if parameter_observation is not None:
            source = parameter_observation.get("selected_source") \
                or parameter_observation.get("source_type") or "未形成可用来源"
            allowed = parameter_observation.get("allowed_for_trial") is True
            next_action = (
                "选择简化试切或完整试切。" if allowed
                else "补全有效设备配置，或明确授权生成仅限试切的探索候选。"
            )
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
    def _latest_parameter_truth(
        observations: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        for observation in reversed(observations):
            data = observation.get("data") or {}
            if not isinstance(data, dict):
                continue
            process_parameters = data.get("process_parameters") or {}
            strategy_parameters = data.get("strategy_parameters") or {}
            if isinstance(process_parameters, dict) and isinstance(strategy_parameters, dict):
                parameters = {**process_parameters, **strategy_parameters}
                if parameters:
                    return parameters
        return {}

    @staticmethod
    def _latest_equipment_truth(observations: list[dict[str, Any]]) -> dict[str, Any]:
        for observation in reversed(observations):
            data = observation.get("data") or {}
            if isinstance(data, dict) and isinstance(data.get("tunable_capabilities"), dict):
                return data
        return {}

    @staticmethod
    def _validate_process_parameter_semantics(
        process: ProcessPlan,
        parameter_truth: dict[str, dict[str, Any]],
        equipment_truth: dict[str, Any],
    ) -> None:
        tunable = set((equipment_truth.get("tunable_capabilities") or {}).keys())
        fixed = equipment_truth.get("fixed_conditions") or {}
        for name, value in process.fixed_conditions.items():
            if name in tunable:
                parameter = parameter_truth.get(name) or {}
                if parameter.get("role") != "process_setpoint" or parameter.get("value") != value:
                    raise ValueError(
                        f"tunable_fixed_for_trial_requires_matching_tool_truth:{name};"
                        "move_to_process_setpoint_candidate_or_remove"
                    )
            if name in fixed and value != fixed[name]:
                raise ValueError(f"fixed_equipment_condition_mismatch:{name}")

        declared_controls: set[str] = set()
        for variable in process.controllable_variables:
            name = variable.get("name")
            if not isinstance(name, str) or not name:
                continue
            role = MainAgentPlanner._canonical_parameter_role(
                str(variable.get("role") or "process_setpoint")
            )
            if role in {"process_setpoint", "strategy_parameter"} \
                    and variable.get("selected_for_trial") is not False:
                declared_controls.add(name)
            if name in tunable and role != "process_setpoint":
                raise ValueError(f"equipment_tunable_must_be_process_setpoint:{name}")
        missing_truth = sorted(declared_controls - set(parameter_truth))
        if missing_truth:
            raise ValueError(
                f"controllable_variable_requires_parameter_tool_truth:{','.join(missing_truth)}"
            )

    @staticmethod
    def _canonical_parameter_role(value: str) -> str:
        aliases = {
            "process_setpoint": "process_setpoint",
            "process setpoint": "process_setpoint",
            "工艺设定值": "process_setpoint",
            "工艺参数": "process_setpoint",
            "strategy_parameter": "strategy_parameter",
            "strategy parameter": "strategy_parameter",
            "策略参数": "strategy_parameter",
        }
        return aliases.get(value.strip().lower(), value.strip())

    @staticmethod
    def _validate_trial_parameter_truth(
        trial: TrialPlan,
        parameter_truth: dict[str, dict[str, Any]],
    ) -> None:
        truth_names = set(parameter_truth)
        compared_fields = {
            "name", "value", "unit", "role", "source_type", "source_refs",
            "authority_level", "uncertainty", "validated", "allowed_for_trial",
            "allowed_for_formal_process", "allowed_for_bo_training",
        }
        for candidate in trial.parameter_candidates:
            if set(candidate.parameters) != truth_names:
                raise ValueError("trial_parameter_names_must_match_latest_tool_result")
            for name, parameter in candidate.parameters.items():
                actual = parameter.model_dump(mode="json")
                expected = parameter_truth[name]
                if any(actual.get(field) != expected.get(field) for field in compared_fields):
                    raise ValueError(f"trial_parameter_provenance_mismatch:{name}")

    @staticmethod
    def _validate_self_contained_plan_message(message: str) -> None:
        lowered = message.lower()
        if len(message.strip()) < 80 or any(
            marker in message for marker in ("详见上下文", "见上下文中的", "见 Context", "见context")
        ):
            raise ValueError("final_answer_must_be_self_contained")
        concepts = {
            "strategy": ("策略", "路线", "strategy"),
            "trial": ("试切", "trial"),
            "evaluation": ("检测", "评价", "测量", "判据"),
            "adaptation": ("调整", "迭代", "下一轮"),
            "provenance": ("来源", "可信", "未经验证", "provenance"),
            "risk": ("风险", "警告", "提醒"),
        }
        missing = [
            name for name, markers in concepts.items()
            if not any(marker.lower() in lowered for marker in markers)
        ]
        if missing:
            raise ValueError(f"final_answer_missing_concepts:{','.join(missing)}")

    @staticmethod
    def _complete_plan_required(working_context: dict[str, Any]) -> bool:
        task = working_context.get("task") or {}
        geometry = task.get("geometry") or {}
        if not (task.get("material") and task.get("process_intent") and geometry.get("feature_type")):
            return False
        if geometry.get("feature_type") == "rectangular_groove" \
                and geometry.get("depth_mm") is None and not geometry.get("through"):
            return False
        return True

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
        raw.setdefault("arguments", raw.get("args") or {})
        raw.setdefault("context_updates", {})
        raw.setdefault("message", raw.get("answer") or raw.get("content"))
        raw.setdefault("decision_summary", str(raw.get("reason") or "执行主 Agent 选择的下一动作。"))
        skills_used = raw.get("skills_used")
        if skills_used is None and raw.get("skill"):
            raw["skills_used"] = [raw["skill"]]
        raw.setdefault("skills_used", [])
        if raw.get("action") == "respond" and isinstance(raw.get("message"), str):
            raw["message"] = MainAgentPlanner._strip_terminal_confirmation(raw["message"])
        return raw

    @staticmethod
    def _strip_terminal_confirmation(message: str) -> str:
        text = re.sub(r"(?:请)?确认后(?:即可|可以|可)?", "", message)
        text = re.sub(
            r"(?m)^.*(?:是否接受|是否开始|请确认是否|如无问题.*(?:确认|回复)).*(?:\n|$)",
            "", text,
        )
        return text.strip()

    @staticmethod
    def _protect_established_task_facts(
        raw: dict[str, Any], working_context: dict[str, Any], user_message: str,
    ) -> dict[str, Any]:
        updates = raw.get("context_updates")
        if not isinstance(updates, dict) or not isinstance(updates.get("task"), dict):
            return raw
        if re.search(r"改为|改成|更正|修正|调整为|应为|换成|不是.+(?:而是|是)", user_message):
            return raw
        missing = object()

        def additions(current: Any, proposed: Any) -> Any:
            if isinstance(current, dict) and isinstance(proposed, dict):
                result: dict[str, Any] = {}
                for key, value in proposed.items():
                    if key not in current:
                        result[key] = value
                        continue
                    child = additions(current[key], value)
                    if child is not missing:
                        result[key] = child
                return result if result else missing
            if isinstance(current, list) and isinstance(proposed, list):
                merged = list(current)
                for item in proposed:
                    if item not in merged:
                        merged.append(item)
                return merged if merged != current else missing
            return missing

        protected = additions(working_context.get("task") or {}, updates["task"])
        normalized = dict(raw)
        normalized_updates = dict(updates)
        if protected is missing:
            normalized_updates.pop("task", None)
        else:
            normalized_updates["task"] = protected
        normalized["context_updates"] = normalized_updates
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
    def _system_prompt() -> str:
        return (
            "你是超快激光加工前台唯一主 Agent。每次只返回一个 JSON 对象，不输出 Markdown。"
            "字段仅包括 action,decision_summary,skills_used,tool_name,arguments,message,context_updates。"
            "action 仅限 update_context、call_tool、ask_user、respond；Skill 不是行动，不得加载或卸载 Skill。"
            "update_context 只更新事实并继续规划；respond 只结束当前对话轮次，不表示加工任务完成。"
            "一次读取用户消息、Working Context、相关 Observation、注入的 Skill 指导和 Tool Schema。"
            "Tool 是外部能力；需要证据、设备事实、参数计算或执行时选择一个 Tool，Tool 返回后再决策。"
            "同一行动可以提交明确的 context_updates；不得逐字段写状态，也不得重复查询相同 Tool。"
            "只有缺失信息会实质改变加工路线且无法安全假设时才 ask_user；按阻塞信息量提出 1 至 5 个问题，"
            "只有一个阻塞字段时只问一个，不得为凑数量询问非阻塞偏好。"
            "不得询问应由系统规划的功率、频率、速度等参数。"
            "方案结构、工艺变量和评价指标必须按当前任务动态选择，不套用通孔、切割或其他案例模板。"
            "参数必须区分设备固定条件、设备可调能力、工艺设定值、策略参数和派生指标。"
            "设备范围只是边界，不能用范围中点冒充推荐；不得改写 Tool 返回的证据和 provenance。"
            "所有参数推荐只能调用 recommend_process_parameters；该 Tool 内部强制 BO→RAG→受控探索顺序，"
            "不得请求或伪造其内部子步骤。"
            "加工任务信息足够时继续调用必要 Tool，并用 respond 返回当前阶段结论和明确 NextAction。"
            "真实设备动作仍须遵守 Tool 的安全边界和当次用户授权。"
        )

    @staticmethod
    def _prompt(
        message: str,
        working_context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        skill_guidance: list[dict[str, Any]],
        recent_tool_results: list[dict[str, Any]],
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
        return "\n".join([
            f"wire_example={json.dumps(wire_example, ensure_ascii=False)}",
            f"user_message={json.dumps(message, ensure_ascii=False)}",
            f"working_context={json.dumps(working_context, ensure_ascii=False)}",
            f"relevant_observations={json.dumps(recent_tool_results, ensure_ascii=False)}",
            f"injected_skill_guidance={json.dumps(skill_guidance, ensure_ascii=False)}",
            f"available_tools={json.dumps(available_tools, ensure_ascii=False)}",
            f"runtime_hints={json.dumps(runtime_hints, ensure_ascii=False)}",
        ])

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
