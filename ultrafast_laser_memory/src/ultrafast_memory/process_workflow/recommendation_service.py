from __future__ import annotations

import json
from typing import Any

from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_integrations.storage.read_models import list_bo_training_samples
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.rag.query_service import query_rag

from .policy import ParameterRecommendationPolicy, validate_parameter_constraints
from .schemas import ParameterRecommendation
from .tools import (bo_parameter_recommendation_tool, llm_fallback_parameter_tool,
                    rag_parameter_recommendation_tool)


UNITS = {
    "laser_power_W": "W", "frequency_kHz": "kHz", "scan_speed_mm_s": "mm/s",
    "pulse_width_fs": "fs", "spot_diameter_um": "um", "passes": "count",
    "hatch_spacing_um": "um", "layer_step_um": "um",
}


def recommend_trial_parameters(task: dict[str, Any], equipment: dict[str, Any],
                               *, allow_llm_fallback: bool = False) -> tuple[ParameterRecommendation, list[str]]:
    samples = list_bo_training_samples()
    query = " ".join(str(task.get(key) or "") for key in ("material", "process_type", "thickness_mm"))
    rag = query_rag({"query": query, "top_k": 8, "purpose": "simple_trial"})
    context = {
        "task_id": task.get("task_id"), "task_spec": task, "samples": samples,
        "rag_hits": rag.get("hits") or [], "extracted_parameters": [],
        "equipment_bounds": equipment.get("machine_bounds") or {},
        "equipment_hard_bounds_complete": bool(equipment.get("active") and not equipment.get("missing_equipment_fields")),
        "allow_llm_fallback": allow_llm_fallback, "user_allows_exploration": allow_llm_fallback,
        "trial_allowed": True, "intended_use": "simple_trial",
    }
    if len(samples) >= 10:
        raw = LegacyBOCompatibilityAdapter().recommend(task, samples, equipment)
        context["bo_candidates"] = [
            {"name": name, "value": value, "unit": UNITS.get(name, "unknown"),
             "source_refs": [f"bo_dataset:{raw.get('sample_count', 0)}"], "confidence": 0.7,
             "historically_validated": False}
            for name, value in (raw.get("recommended_parameters") or {}).items()
        ]

    def fallback_tool(tool_context: dict[str, Any]) -> ParameterRecommendation:
        return llm_fallback_parameter_tool({**tool_context, "policy_authorized": True}, _llm_candidates)

    policy = ParameterRecommendationPolicy(
        bo_parameter_recommendation_tool, rag_parameter_recommendation_tool,
        fallback_tool if allow_llm_fallback else None, validate_parameter_constraints)
    try:
        result = policy.recommend(context)
    except Exception as exc:
        result = ParameterRecommendation(
            recommendation_id=f"blocked-{task.get('task_id', 'task')}", recommendation_mode="blocked",
            support_status="insufficient", authority_level="none", intended_use="simple_trial",
            warnings=[f"controlled parameter tool failed: {type(exc).__name__}"])
    return result, policy.call_order


def _llm_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
    client = create_llm_client(get_llm_config())
    bounds = context.get("equipment_bounds") or {}
    prompt = {
        "task": context.get("task_spec") or {}, "equipment_hard_bounds": bounds,
        "instruction": ("Return JSON only: an array of at most 3 exploratory simple-trial parameter objects. "
                        "Each object must contain name,value,unit,source_refs,confidence. Do not claim validation."),
    }
    response = client.chat([
        {"role": "system", "content": "You are a constrained parameter hypothesis tool, not a chat assistant."},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}], temperature=0)
    content = (response.get("content") or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
        if content.lstrip().startswith("json"):
            content = content.lstrip()[4:].lstrip()
    value = json.loads(content)
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise ValueError("fallback tool must return 1-3 parameter objects")
    return value
