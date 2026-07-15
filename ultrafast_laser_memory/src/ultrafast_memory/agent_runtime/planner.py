from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from ultrafast_memory.agent_runtime.actions import AgentAction


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
    ) -> AgentAction:
        deterministic = self._deterministic_task_action(message, working_context)
        if deterministic is not None:
            return deterministic
        if self.client is None or getattr(self.client, "provider", None) == "mock":
            return AgentAction(
                action="ask_user",
                decision_summary="主 Agent LLM 当前不可用，无法可靠解释该自由文本。",
                message="当前无法可靠理解这条信息，请稍后重试；现有任务状态未被修改，已有上下文未被清空。",
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
                options: dict[str, Any] = {"temperature": 0, "timeout": 25}
                if attempt == 0:
                    options["response_format"] = {"type": "json_object"}
                repair = "" if attempt == 0 else "\n" + self._repair_note(last_error)
                result = self.client.chat([
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt + repair},
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
            except Exception as exc:  # noqa: BLE001 - retried then sanitized
                last_error = exc

        return AgentAction(
            action="ask_user",
            decision_summary=f"主 Agent 行动规划失败：{type(last_error).__name__ if last_error else 'unknown'}。",
            message="我暂时无法安全规划下一步；现有状态未被修改，已有任务上下文和观察均已保留。请稍后重试。",
            provider=getattr(self.client, "provider", None),
            model=getattr(self.client, "model", None),
            error_details=self._safe_error_details(last_error),
        )

    @staticmethod
    def _validate_action(raw: dict[str, Any], available_tool_names: list[str], skill_names: list[str]) -> AgentAction:
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
        return raw

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
            "把用户明确事实直接写入 context_updates.task；Working Context 是开放结构，允许部分信息和自定义几何。"
            "同一行动可同时更新上下文并追问、调用工具或回答；不存在独立的任务状态写入工具。"
            "关键歧义（如槽深、通孔或盲孔）必须立即追问；功率、频率、速度等工艺参数应由系统推荐，不询问用户。"
            "所有前台安全 Tool 始终可见；Skill 只提供专业指导和排序提示。"
            "Tool 结果是真实来源：不得改写 BO/RAG provenance，不得把 exploratory 参数冒充已验证参数。"
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
            "message": "矩形槽的目标深度是多少？",
            "context_updates": {"task": {"process_intent": "groove_machining"}},
        }
        return "\n".join([
            f"wire_example={json.dumps(example, ensure_ascii=False)}",
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
            return AgentAction(
                action="final_answer", decision_summary="已记录用户明确提供的材料事实。",
                message="已记录材料；现有任务状态已更新，可继续补充加工目标。",
                context_updates={"task": {"material": {"name": normalized, "description": raw}}},
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
                size_text = f"{float(groove.group('length')) * factor:g}×{float(groove.group('width')) * factor:g} mm"
                return AgentAction(
                    action="ask_user", decision_summary="槽深会显著改变加工路线和参数空间，必须先确认。",
                    message=f"已识别材料和 {size_text} 矩形槽。矩形槽的目标深度是多少（或是否贯穿）？",
                    context_updates=updates, provider="deterministic_task_intake", model="open-geometry-adapter",
                )
            return AgentAction(
                action="final_answer", decision_summary="已识别矩形槽任务的明确事实。",
                message="已记录材料、矩形槽尺寸及深度要求，可继续进行工艺分析。",
                context_updates=updates, provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        current_geometry = task.get("geometry")
        depth = cls._depth_from_message(text, allow_bare=isinstance(current_geometry, dict))
        if depth is not None and isinstance(current_geometry, dict) and current_geometry.get("feature_type") == "rectangular_groove":
            return AgentAction(
                action="final_answer", decision_summary="已记录用户补充的关键槽深。",
                message="已记录矩形槽目标深度，可继续进行工艺路线与参数分析。",
                context_updates={"task": {"geometry": {"depth_mm": depth}}},
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        cfrp = re.search(r"切割\s*(?P<thickness>\d+(?:\.\d+)?)\s*(?:mm|毫米)厚的?(?P<material>碳纤维(?:复合板|复合材料|板)?)", text)
        if cfrp:
            thickness = float(cfrp.group("thickness"))
            return AgentAction(
                action="final_answer", decision_summary="已识别 CFRP 切割任务事实；工艺参数应由系统计算。",
                message=f"已识别为碳纤维复合板切割，板厚 {thickness:g} mm。后续将基于当前设备边界推荐工艺参数，不需要您提供激光功率。",
                context_updates={"task": {
                    "material": {"name": "CFRP", "description": cfrp.group("material")},
                    "process_intent": "cutting",
                    "geometry": {"feature_type": "sheet_cut", "workpiece_thickness_mm": thickness},
                }},
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )

        diamond = re.search(
            r"(?:在)?(?P<thickness>\d+(?:\.\d+)?)\s*(?:mm|毫米)厚的?金刚石(?:上|中)?加工(?:一个)?"
            r"直径\s*(?P<diameter>\d+(?:\.\d+)?)\s*(?:mm|毫米)的?通孔", text,
        )
        if diamond:
            thickness = float(diamond.group("thickness"))
            diameter = float(diamond.group("diameter"))
            return AgentAction(
                action="final_answer", decision_summary="已识别金刚石通孔的完整开放几何。",
                message=f"已记录 {thickness:g} mm 厚金刚石上的直径 {diameter:g} mm 通孔任务，可继续进行工艺分析。",
                context_updates={"task": {
                    "material": {"name": "diamond", "description": "金刚石", "thickness_mm": thickness},
                    "process_intent": "hole_drilling",
                    "geometry": {"feature_type": "through_hole", "dimensions": {"diameter_mm": diameter}, "through": True},
                }},
                provider="deterministic_task_intake", model="open-geometry-adapter",
            )
        return None

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
            "修复要求：只返回一个行动 JSON；context_updates 必须是对象；不要调用未注册的状态写入工具。"
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
