from __future__ import annotations

import json
from typing import Any

from ultrafast_agent.task_intake.schemas import (
    ALLOWED_TASK_FIELDS,
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)


class LLMStructuredExtractor:
    def __init__(self, client: Any | None):
        self.client = client

    def extract(
        self,
        message: str,
        current_spec: dict[str, Any],
        context: ClarificationContext,
    ) -> TaskSpecPatch:
        if self.client is None or getattr(self.client, "provider", None) == "mock":
            return TaskSpecPatch(
                unresolved_fields=list(context.pending_fields),
                ambiguities=[{"reason": "llm_unavailable"}],
                llm_attempted=True,
                degraded=True,
                provider=getattr(self.client, "provider", None),
                model=getattr(self.client, "model", None),
                extraction_mode="llm_structured",
            )
        prompt = self._prompt(message, current_spec, context)
        last_reason = "llm_extraction_failed"
        provider = getattr(self.client, "provider", None)
        model = getattr(self.client, "model", None)
        for attempt in range(1, 3):
            try:
                options: dict[str, Any] = {"temperature": 0, "timeout": 20}
                if attempt == 1:
                    options["response_format"] = self._response_format()
                result = self.client.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是字段语义抽取器，只返回符合给定 JSON Schema 的 JSON。"
                                "不得回答用户，不得建议参数，不得暴露推理过程。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    **options,
                )
                data = self._json(result.get("content") or "")
                return self._validated_patch(
                    data,
                    context,
                    provider=result.get("provider") or provider,
                    model=result.get("model") or model,
                    attempt_count=attempt,
                )
            except Exception as exc:
                last_reason = f"llm_extraction_failed:{type(exc).__name__}"
        return TaskSpecPatch(
            unresolved_fields=list(context.pending_fields),
            ambiguities=[{"reason": last_reason}],
            llm_attempted=True,
            degraded=True,
            provider=provider,
            model=model,
            extraction_mode="llm_structured",
            attempt_count=2,
        )

    @staticmethod
    def _json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise TypeError("LLM extraction response must be an object")
        return value

    @staticmethod
    def _validated_patch(
        data: dict[str, Any],
        context: ClarificationContext,
        *,
        provider: str | None,
        model: str | None,
        attempt_count: int,
    ) -> TaskSpecPatch:
        accepted = []
        rejected = []
        raw_updates = data.get("updates") or []
        if not isinstance(raw_updates, list):
            raise TypeError("updates must be a list")
        for raw in raw_updates:
            if not isinstance(raw, dict):
                rejected.append({"reason": "candidate_not_object"})
                continue
            if "raw_value" not in raw and "value" in raw:
                raw = {**raw, "raw_value": raw["value"]}
            candidate_data = {
                **raw,
                "extraction_source": "llm_semantic_extraction",
                "confidence": float(raw.get("confidence", 0)),
            }
            accepted.append(TaskFieldCandidate.model_validate(candidate_data))
        unresolved = data.get("unresolved_fields") or []
        ambiguities = data.get("ambiguities") or []
        if not isinstance(unresolved, list) or not isinstance(ambiguities, list):
            raise TypeError("invalid unresolved_fields or ambiguities")
        return TaskSpecPatch(
            updates=accepted,
            unresolved_fields=[str(field) for field in unresolved if str(field) in context.pending_fields],
            ambiguities=[item for item in ambiguities if isinstance(item, dict)],
            rejected_candidates=rejected,
            llm_attempted=True,
            extraction_version="llm-task-intake-v1",
            provider=provider,
            model=model,
            extraction_mode="llm_structured",
            attempt_count=attempt_count,
        )

    @staticmethod
    def _prompt(message: str, current_spec: dict[str, Any], context: ClarificationContext) -> str:
        schema = LLMStructuredExtractor._response_format()["json_schema"]["schema"]
        return (
            "任务：从用户原文抽取用户明确表达的任务字段。\n"
            "约束：1.只提取用户明确表达的内容；2.结合上一轮问题理解“允许”“无”等简答；"
            "3.不得推测缺失信息；4.不得生成激光功率、频率、扫描速度、passes等工艺推荐参数；"
            "5.不得修改设备边界；6.不得修改工作流阶段或会话状态；7.不得输出白名单外字段；"
            "8.每个更新必须提供当前用户原文 evidence；9.无法确定时返回 unresolved_fields 或 ambiguities；"
            "10.只有用户明确说出改为、更正、说错了或不是…是…时 operation 才能为 correct，"
            "且 evidence 必须包含修正语义。只输出 JSON，不输出解释。\n"
            f"user_message={json.dumps(message, ensure_ascii=False)}\n"
            f"current_task_spec={json.dumps(current_spec, ensure_ascii=False)}\n"
            f"missing_fields={json.dumps(context.pending_fields, ensure_ascii=False)}\n"
            f"previous_questions={json.dumps(context.previous_questions, ensure_ascii=False)}\n"
            f"current_process_type={json.dumps(current_spec.get('process_type'), ensure_ascii=False)}\n"
            f"expected_answer_types={json.dumps(context.expected_answer_types, ensure_ascii=False)}\n"
            f"JSON Schema={json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "task_spec_patch",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["updates", "unresolved_fields", "ambiguities", "extractor_version"],
                    "properties": {
                        "updates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "field_name",
                                    "raw_value",
                                    "unit",
                                    "evidence",
                                    "confidence",
                                    "operation",
                                ],
                                "properties": {
                                    "field_name": {"type": "string", "enum": sorted(ALLOWED_TASK_FIELDS)},
                                    "raw_value": {"type": ["string", "number", "boolean", "null"]},
                                    "unit": {"type": ["string", "null"]},
                                    "evidence": {"type": "string"},
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "operation": {"type": "string", "enum": ["fill", "correct"]},
                                    "ambiguity": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "unresolved_fields": {"type": "array", "items": {"type": "string"}},
                        "ambiguities": {"type": "array", "items": {"type": "object"}},
                        "extractor_version": {"type": "string", "const": "llm-task-intake-v1"},
                    },
                },
            },
        }


# Import compatibility for callers created before the LLM-primary migration.
LLMTaskFieldExtractor = LLMStructuredExtractor
