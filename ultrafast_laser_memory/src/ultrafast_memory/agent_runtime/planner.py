from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from ultrafast_memory.agent_runtime.actions import AgentAction
from ultrafast_domain.process import ProcessPlan
from ultrafast_domain.trial import TrialPlan


class MainAgentPlanner:
    """Choose one next action. Working Context is updated by the loop, not a tool."""

    def __init__(self, client: Any):
        self.client = client

    def decide(
        self,
        *,
        message: str,
        working_context: dict[str, Any],
        available_tools: list[dict[str, Any]] | None = None,
        active_skills: list[str] | None = None,
        recent_tool_results: list[dict[str, Any]] | None = None,
        skill_catalog: list[dict[str, Any]] | None = None,
        runtime_hints: dict[str, Any] | None = None,
        model_call_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentAction:
        deterministic = self._deterministic_task_action(message, working_context)
        if deterministic is not None:
            return deterministic
        if self.client is None or getattr(self.client, "provider", None) == "mock":
            return AgentAction(
                action="final_answer",
                decision_summary="主 Agent LLM 当前不可用，无法可靠解释该自由文本。",
                message=(
                    "主 Agent 模型当前不可用，无法可靠生成专业加工方案。"
                    "现有任务状态未被修改，已识别的事实和 Observation 均已保留；请稍后重试。"
                ),
                provider=getattr(self.client, "provider", None),
                model=getattr(self.client, "model", None),
            )

        tools = available_tools or []
        catalog = skill_catalog or []
        prompt = self._prompt(
            message, working_context, tools, active_skills or [],
            recent_tool_results or [], catalog, runtime_hints or {},
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                options: dict[str, Any] = {"temperature": 0, "timeout": 60}
                if attempt == 0:
                    options["response_format"] = {"type": "json_object"}
                repair = "" if attempt == 0 else "\n" + self._repair_note(last_error)
                self._emit_model_call(model_call_sink, attempt + 1, int(options["timeout"]))
                result = self.client.chat([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt + repair},
                ], **options)
                raw = self._normalize_provider_action(self._json(result.get("content") or ""), message)
                raw = self._protect_established_task_facts(raw, working_context, message)
                action = self._validate_action(
                    raw,
                    [item["name"] for item in tools],
                    [item["name"] for item in catalog],
                    working_context,
                    recent_tool_results or [],
                )
                return action.model_copy(update={
                    "provider": result.get("provider") or getattr(self.client, "provider", None),
                    "model": result.get("model") or getattr(self.client, "model", None),
                })
            except Exception as exc:  # noqa: BLE001 - retried then sanitized
                last_error = exc

        return AgentAction(
            action="final_answer",
            decision_summary=f"主 Agent 行动规划失败：{type(last_error).__name__ if last_error else 'unknown'}。",
            message=(
                "主 Agent 连续两次未能产生有效的结构化行动。"
                "现有状态未被修改，已有上下文和观察均已保留；这是可恢复的模型规划错误，请稍后重试。"
            ),
            provider=getattr(self.client, "provider", None),
            model=getattr(self.client, "model", None),
            error_details=self._safe_error_details(last_error),
        )

    def _emit_model_call(
        self,
        sink: Callable[[dict[str, Any]], None] | None,
        attempt: int,
        timeout_s: int,
    ) -> None:
        if sink is None:
            return
        try:
            sink({
                "provider": getattr(self.client, "provider", None),
                "model": getattr(self.client, "model", None),
                "component": "main_agent_planner",
                "attempt": attempt,
                "timeout_s": timeout_s,
            })
        except Exception:  # noqa: BLE001 - observability cannot block planning
            return

    @staticmethod
    def _validate_action(
        raw: dict[str, Any],
        available_tool_names: list[str],
        skill_names: list[str],
        working_context: dict[str, Any] | None = None,
        recent_tool_results: list[dict[str, Any]] | None = None,
    ) -> AgentAction:
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
        if action.action == "final_answer" and MainAgentPlanner._complete_plan_required(working_context or {}):
            updates = action.context_updates or {}
            process = ProcessPlan.model_validate(
                updates.get("process_plan") or (working_context or {}).get("process_plan")
            )
            trial = TrialPlan.model_validate(
                updates.get("trial_plan") or (working_context or {}).get("trial_plan")
            )
            MainAgentPlanner._validate_self_contained_plan_message(action.message or "")
            if updates.get("trial_plan") is not None:
                parameter_truth = MainAgentPlanner._latest_parameter_truth(recent_tool_results or [])
                if not parameter_truth:
                    raise ValueError("new_trial_plan_requires_successful_parameter_tool_result")
                equipment_truth = MainAgentPlanner._latest_equipment_truth(recent_tool_results or [])
                MainAgentPlanner._validate_process_parameter_semantics(
                    process, parameter_truth, equipment_truth,
                )
                MainAgentPlanner._validate_trial_parameter_truth(trial, parameter_truth)
        return action

    @staticmethod
    def _latest_parameter_truth(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
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
                if (
                    parameter.get("role") != "process_setpoint"
                    or parameter.get("value") != value
                ):
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
            role = MainAgentPlanner._canonical_parameter_role(str(variable.get("role") or "process_setpoint"))
            if role in {"process_setpoint", "strategy_parameter"} and variable.get("selected_for_trial") is not False:
                declared_controls.add(name)
            if name in tunable and role != "process_setpoint":
                raise ValueError(f"equipment_tunable_must_be_process_setpoint:{name}")
        missing_truth = sorted(declared_controls - set(parameter_truth))
        if missing_truth:
            raise ValueError(f"controllable_variable_requires_parameter_tool_truth:{','.join(missing_truth)}")

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
        required_concepts = {
            "strategy": ("策略", "路线", "strategy"),
            "trial": ("试切", "trial"),
            "evaluation": ("检测", "评价", "测量", "判据"),
            "adaptation": ("调整", "迭代", "下一轮"),
            "provenance": ("来源", "可信", "未经验证", "provenance"),
            "risk": ("风险", "警告", "提醒"),
        }
        missing = [
            name for name, markers in required_concepts.items()
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
            "request_clarification": "ask_user", "answer": "final_answer",
        }
        raw["action"] = aliases.get(str(raw.get("action") or raw.get("type") or ""), raw.get("action"))
        raw.setdefault("tool_name", raw.get("tool"))
        raw.setdefault("skill_name", raw.get("skill"))
        raw.setdefault("arguments", raw.get("args") or {})
        raw.setdefault("context_updates", {})
        raw.setdefault("message", raw.get("answer") or raw.get("content"))
        raw.setdefault("decision_summary", str(raw.get("reason") or "执行主 Agent 选择的下一动作。"))
        if raw.get("action") == "final_answer" and isinstance(raw.get("message"), str):
            raw["message"] = MainAgentPlanner._strip_terminal_confirmation(raw["message"])
        return raw

    @staticmethod
    def _strip_terminal_confirmation(message: str) -> str:
        """Remove non-blocking acceptance/start invitations from a completed answer."""
        text = re.sub(r"(?:请)?确认后(?:即可|可以|可)?", "", message)
        text = re.sub(
            r"(?m)^.*(?:是否接受|是否开始|请确认是否|如无问题.*(?:确认|回复)).*(?:\n|$)",
            "",
            text,
        )
        return text.strip()

    @staticmethod
    def _protect_established_task_facts(
        raw: dict[str, Any],
        working_context: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        """Planning may add task facts; only explicit user corrections may overwrite them."""
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
            "你是超快激光加工前台唯一主 Agent。每次只返回一个 JSON 行动，不输出 Markdown。"
            "字段：action,decision_summary,skill_name,tool_name,arguments,message,context_updates。"
            "action 仅限 load_skill、unload_skill、call_tool、ask_user、final_answer。"
            "一次读取完整用户消息、文档、Working Context 和 Observations；把本轮全部明确事实一次写入 context_updates.task。"
            "Working Context 是开放结构，允许部分信息和自定义几何；不得拆成逐字段 Tool Call，也不得重复询问已有事实。"
            "同一行动可同时更新上下文并追问、调用工具或回答；不存在独立的任务状态写入工具。"
            "你必须区分五类内容：Blocking Question 是没有答案就无法合理继续；Assumption 是可明确假设后继续；"
            "Reminder、Warning 和 Optional Preference 都不要求用户回答。只有 Blocking Question 使用 ask_user，"
            "且只问完成当前任务真正必要的最少问题，一个问题完全合法。其余四类放入 final_answer。"
            "槽深等会改变路线且无法合理假设的信息才是 Blocking Question；未指定质量偏好、参数未经验证、"
            "是否接受方案都不是 Blocking Question。功率、频率、速度等工艺参数由系统规划，不询问用户。"
            "所有前台安全 Tool 始终可见；Skill 只提供专业指导和排序提示。"
            "已加载 Skill 是稳定专业执行协议，必须按其 method、required considerations、output expectations、"
            "prohibitions 和 failure handling 执行，而不是把 Skill 当能力标签。"
            "参数必须分为设备固定条件、设备可调能力、工艺设定值、策略参数和派生指标。"
            "固定条件不得进入推荐工艺参数；设备范围只是安全约束，不得用边界中点生成推荐。"
            "Tool 结果是真实来源：不得改写 BO/RAG provenance，不得把 exploratory 参数冒充已验证参数。"
            "探索候选必须由 ProcessPlan 选择变量，由你基于材料、几何、路线和风险提出少量有理由的 candidate，"
            "再交给 propose_exploratory_parameters 做边界检查。"
            "准备调用参数 Tool 时，应先加载 parameter_recommendation Skill；准备形成 TrialPlan 时，应加载 "
            "experiment_optimization Skill。Skill 提供方法指导，不改变 Tool 可见性。"
            "ProcessPlan 中本轮每个 controllable_variable 都必须进入参数 Tool；仅明确 "
            "selected_for_trial=false 的后续变量可以不进入当前候选。"
            "设备 tunable_capabilities 中的变量只能是 process_setpoint，min/max 不是固定条件或推荐值。"
            "设备可调量只有作为参数 Tool 验证过的 process_setpoint 才能在本轮保持固定；"
            "不得把设备下限、上限直接写成 fixed_conditions。"
            "当加工任务信息足以继续时，应组合必要 Skill 和 Tool，形成完整 ProcessPlan 与第一轮 TrialPlan。"
            "ProcessPlan 和 TrialPlan 是开放语义结构：只规定目标、策略、操作、相关变量、评价和迭代逻辑，"
            "具体路径、分层、焦点、参数和检测指标必须按当前任务动态选择，不得套用其他加工类型模板。"
            "final_answer 必须综合任务、设备、策略、参数、检测、判据、调整逻辑、来源和风险；"
            "同时把可验证的结构分别写入 context_updates.process_plan 和 context_updates.trial_plan。"
            "形成有用 TrialPlan 后必须 final_answer，不得自动追加是否接受、是否开始或是否还有要求。"
            "最终用户回复必须自包含任务、策略、试切参数、检测与判据、调整逻辑、来源、风险；"
            "不得让用户去看内部 context_updates、process_plan 或 trial_plan。"
            "新生成的 TrialPlan 候选参数必须逐字段复制本轮成功参数 Tool 的 process_parameters 和 "
            "strategy_parameters，"
            "不得改写 value、source_type、authority_level、uncertainty 或权限。"
            "只在设备硬安全、明确 unsafe 或不可逆动作未获本次确认时阻断。"
        )

    @staticmethod
    def _prompt(
        message: str,
        working_context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        active_skills: list[str],
        recent_tool_results: list[dict[str, Any]],
        skill_catalog: list[dict[str, Any]],
        runtime_hints: dict[str, Any],
    ) -> str:
        example = {
            "action": "ask_user",
            "decision_summary": "槽深决定路线，先确认。",
            "skill_name": None,
            "tool_name": None,
            "arguments": {},
            "message": "矩形槽的目标深度是多少，还是要求贯穿？",
            "context_updates": {"task": {"process_intent": "groove_machining"}},
        }
        professional_output_contract = {
            "process_plan_shape": {
                "objective": "string", "strategy": "object", "operations": "array<object>",
                "fixed_conditions": "object", "controllable_variables": "array<object>",
                "evaluation_plan": "array<object>", "risks": "array<object>",
                "assumptions": "array<string>", "adaptation_guidance": "array<object>",
            },
            "trial_plan_shape": {
                "objective": "string", "hypothesis": "string|null", "setup": "object",
                "strategy": "object", "parameter_candidates": "array<ParameterCandidate>",
                "evaluation_plan": "array<object>", "success_criteria": "array<object>",
                "stop_conditions": "array<object>", "adaptation_guidance": "array<object>",
                "provenance": "array<object>", "warnings": "array<string>",
            },
            "parameter_candidate_shape": {
                "parameters": "object mapping parameter name to ParameterValue",
            },
            "parameter_value_required": [
                "name", "value", "unit", "role", "source_type", "source_refs",
                "authority_level", "uncertainty", "validated", "allowed_for_trial",
                "allowed_for_formal_process", "allowed_for_bo_training",
            ],
        }
        return "\n".join([
            f"wire_example={json.dumps(example, ensure_ascii=False)}",
            f"professional_output_contract={json.dumps(professional_output_contract, ensure_ascii=False)}",
            f"user_message={json.dumps(message, ensure_ascii=False)}",
            f"working_context={json.dumps(working_context, ensure_ascii=False)}",
            f"recent_tool_results={json.dumps(recent_tool_results[-5:], ensure_ascii=False)}",
            f"active_skills={json.dumps(active_skills, ensure_ascii=False)}",
            f"skill_catalog={json.dumps(skill_catalog, ensure_ascii=False)}",
            f"available_tools={json.dumps(available_tools, ensure_ascii=False)}",
            f"runtime_hints={json.dumps(runtime_hints, ensure_ascii=False)}",
        ])

    @classmethod
    def _deterministic_task_action(cls, message: str, working_context: dict[str, Any]) -> AgentAction | None:
        task = dict(working_context.get("task") or {})
        text = message.strip()
        explicit_material = re.fullmatch(r"材料\s*[=＝:：]\s*(.+?)\s*", text)
        if explicit_material:
            raw = explicit_material.group(1)
            normalized = "diamond" if raw in {"金刚石", "钻石"} else raw
            updates = {"task": {"material": {"name": normalized, "description": raw}}}
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="task_understanding",
                decision_summary="一次提交用户明确提供的材料事实，并继续理解当前任务。",
                context_updates=updates,
                provider="deterministic_task_intake", model="open-context-adapter",
            )
        groove = re.search(
            r"^(?:在)?(?P<material>.+?)(?:上|中)加工\s*(?P<length>\d+(?:\.\d+)?)\s*[*xX×]\s*"
            r"(?P<width>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|um|μm|µm)?\s*的?矩形槽",
            text, re.I,
        )
        if groove:
            factor = cls._unit_factor(groove.group("unit") or "mm")
            geometry: dict[str, Any] = {
                "feature_type": "rectangular_groove",
                "dimensions": {
                    "length_mm": float(groove.group("length")) * factor,
                    "width_mm": float(groove.group("width")) * factor,
                },
                "description": f"{groove.group('length')}×{groove.group('width')} mm 矩形槽",
            }
            depth = cls._depth_from_message(text, allow_bare=False)
            if depth is not None:
                geometry["depth_mm"] = depth
            if re.search(r"贯穿|通槽", text):
                geometry["through"] = True
            updates = {"task": {
                "material": {"name": groove.group("material").strip()},
                "process_intent": "groove_machining",
                "geometry": geometry,
            }}
            if depth is None and not geometry.get("through"):
                return AgentAction(
                    action="ask_user", decision_summary="槽深会显著改变加工路线和参数空间，必须先确认。",
                    message="矩形槽的目标深度是多少，还是要求贯穿？",
                    context_updates=updates, provider="deterministic_task_intake", model="open-geometry-adapter",
                )
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="task_understanding",
                decision_summary="一次提交矩形槽任务的全部明确事实，并继续形成工艺方案。",
                context_updates=updates, provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        current_geometry = task.get("geometry")
        depth = cls._depth_from_message(text, allow_bare=isinstance(current_geometry, dict))
        if depth is not None and isinstance(current_geometry, dict) and current_geometry.get("feature_type") == "rectangular_groove":
            updates = {"task": {"geometry": {"depth_mm": depth}}}
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="process_planning",
                decision_summary="记录用户补充的关键槽深，并继续形成工艺与试切方案。",
                context_updates=updates,
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        cfrp = re.search(r"切割\s*(?P<thickness>\d+(?:\.\d+)?)\s*(?:mm|毫米)厚的?(?P<material>碳纤维(?:复合板|复合材料|板)?)", text)
        if cfrp:
            thickness = float(cfrp.group("thickness"))
            updates = {"task": {
                "material": {"name": "CFRP", "description": cfrp.group("material")},
                "workpiece": {"thickness_mm": thickness},
                "process_intent": "cutting",
                "geometry": {"feature_type": "sheet_cut"},
            }}
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="task_understanding",
                decision_summary="一次提交 CFRP 切割任务事实；工艺参数由系统继续规划。",
                context_updates=updates,
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        through_hole = re.search(
            r"(?:在)?(?P<thickness>\d+(?:\.\d+)?)\s*(?:mm|毫米)厚的?"
            r"(?P<material>.+?)(?:上|中)加工(?:一个)?直径\s*"
            r"(?P<diameter>\d+(?:\.\d+)?)\s*(?:mm|毫米)的?通孔", text,
        )
        if through_hole:
            thickness = float(through_hole.group("thickness"))
            diameter = float(through_hole.group("diameter"))
            raw_material = through_hole.group("material").strip()
            material = "diamond" if raw_material in {"金刚石", "钻石"} else raw_material
            updates = {"task": {
                "material": {"name": material, "description": raw_material},
                "workpiece": {"thickness_mm": thickness},
                "process_intent": "through_hole_drilling",
                "geometry": {
                    "feature_type": "through_hole",
                    "dimensions": {"diameter_mm": diameter},
                    "description": f"直径 {diameter:g} mm 通孔",
                    "through": True,
                },
            }}
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="task_understanding",
                decision_summary="一次提交通孔任务的材料、工件和全部几何事实，并继续形成方案。",
                context_updates=updates,
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        diameter_update = re.search(
            r"(?:通孔)?直径\s*(?:改成|改为|调整为|=|：|:)?\s*"
            r"(?P<diameter>\d+(?:\.\d+)?)\s*(?:mm|毫米)", text,
        )
        if diameter_update and isinstance(current_geometry, dict) \
                and current_geometry.get("feature_type") == "through_hole":
            diameter = float(diameter_update.group("diameter"))
            updates = {"task": {"geometry": {
                "dimensions": {"diameter_mm": diameter},
                "description": f"直径 {diameter:g} mm 通孔",
            }}}
            if cls._updates_already_present(working_context, updates):
                return None
            return AgentAction(
                action="load_skill", skill_name="process_planning",
                decision_summary="只更新用户明确修正的通孔直径，保留已有材料与厚度并继续规划。",
                context_updates=updates,
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )
        return None

    @staticmethod
    def _updates_already_present(context: dict[str, Any], updates: dict[str, Any]) -> bool:
        def contains(current: Any, expected: Any) -> bool:
            if isinstance(expected, dict):
                return isinstance(current, dict) and all(
                    key in current and contains(current[key], value)
                    for key, value in expected.items()
                )
            return current == expected

        return contains(context, updates)

    @staticmethod
    def _unit_factor(unit: str) -> float:
        return {"cm": 10.0, "厘米": 10.0, "um": 0.001, "μm": 0.001, "µm": 0.001}.get(unit.lower(), 1.0)

    @classmethod
    def _depth_from_message(cls, message: str, *, allow_bare: bool) -> float | None:
        pattern = r"(?:槽深|深度)\s*(?:为|是|=|：|:)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|um|μm|µm)"
        match = re.search(pattern, message, re.I)
        if not match and allow_bare:
            match = re.fullmatch(r"\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|um|μm|µm)\s*[.。]?\s*", message, re.I)
        return float(match.group("value")) * cls._unit_factor(match.group("unit")) if match else None

    @classmethod
    def _repair_note(cls, exc: Exception | None) -> str:
        return (
            f"previous_output_errors={json.dumps(cls._safe_error_details(exc), ensure_ascii=False)}\n"
            "修复要求：只返回一个行动 JSON；context_updates 必须是对象；不要调用未注册的状态写入工具；"
            "ask_user 只允许真正阻断任务的最少问题；final_answer 加工方案必须同时提供完整 process_plan 和 trial_plan，"
            "且用户文本必须自包含策略、参数、检测判据、调整、来源和风险，不得引用内部上下文代替正文。"
        )

    @staticmethod
    def _safe_error_details(exc: Exception | None) -> list[dict[str, str]]:
        if isinstance(exc, ValidationError):
            return [
                {"loc": ".".join(map(str, item.get("loc") or [])), "type": str(item.get("type") or ""), "msg": str(item.get("msg") or "")}
                for item in exc.errors()
            ]
        if exc is None:
            return []
        return [{"loc": "", "type": type(exc).__name__, "msg": str(exc)[:240]}]
