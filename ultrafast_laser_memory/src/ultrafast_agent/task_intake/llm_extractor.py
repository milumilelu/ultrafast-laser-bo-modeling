from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ultrafast_agent.task_intake.schemas import (
    ALLOWED_TASK_FIELDS,
    ClarificationContext,
    TaskFieldCandidate,
    TaskSpecPatch,
)


class LLMTaskFieldExtractor:
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
            )
        prompt = self._prompt(message, current_spec, context)
        last_reason = "llm_extraction_failed"
        for _ in range(2):
            try:
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
                    temperature=0,
                    timeout=20,
                    response_format=self._response_format(),
                )
                data = self._json(result.get("content") or "")
                return self._validated_patch(data, message, context)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError, Exception) as exc:
                last_reason = f"llm_extraction_failed:{type(exc).__name__}"
        return TaskSpecPatch(
            unresolved_fields=list(context.pending_fields),
            ambiguities=[{"reason": last_reason}],
            llm_attempted=True,
            degraded=True,
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
        message: str,
        context: ClarificationContext,
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
            field = str(raw.get("field_name") or "")
            if field not in ALLOWED_TASK_FIELDS:
                rejected.append(
                    {
                        "field_name": field,
                        "evidence": str(raw.get("evidence") or ""),
                        "reason": "field_not_allowed",
                    }
                )
                continue
            evidence = str(raw.get("evidence") or "").strip()
            if not evidence or evidence not in message:
                rejected.append(
                    {"field_name": field, "evidence": evidence, "reason": "evidence_not_in_user_message"}
                )
                continue
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
        )

    @staticmethod
    def _prompt(message: str, current_spec: dict[str, Any], context: ClarificationContext) -> str:
        schema = LLMTaskFieldExtractor._response_format()["json_schema"]["schema"]
        return (
            "任务：从用户原文抽取用户明确表达的任务字段。\n"
            "规则：不得生成未表达字段；不得生成激光功率、频率、速度或设备边界；"
            "已有值默认不可覆盖，只有明确修正语义才可 operation=correct；无法确定返回 ambiguity。\n"
            f"用户消息={json.dumps(message, ensure_ascii=False)}\n"
            f"当前TaskSpec={json.dumps(current_spec, ensure_ascii=False)}\n"
            f"pending_fields={json.dumps(context.pending_fields, ensure_ascii=False)}\n"
            f"previous_questions={json.dumps(context.previous_questions, ensure_ascii=False)}\n"
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
                    "required": ["updates", "unresolved_fields", "ambiguities"],
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
                                    "operation": {"type": "string", "enum": ["fill", "correct", "clear"]},
                                    "ambiguity": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "unresolved_fields": {"type": "array", "items": {"type": "string"}},
                        "ambiguities": {"type": "array", "items": {"type": "object"}},
                    },
                },
            },
        }

