from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
import json

from .evidence import credibility_summary
from .schemas import ParameterRecommendation, ParameterValue


def assess_data_support(context: dict[str, Any]) -> dict[str, Any]:
    samples = [sample for sample in context.get("samples", []) if _context_match(sample, context)]
    complete = [sample for sample in samples if sample.get("quality_metrics") and not sample.get("excluded")]
    effective = len(complete)
    support = "supported" if effective >= 30 else "partially_supported" if effective >= 10 else "insufficient"
    return {"matched_sample_count": len(samples), "effective_sample_count": effective,
            "support_status": support, "model_mode": "data_driven_bo" if effective >= 30 else
            "hybrid_rule_bo" if effective >= 10 else "rule_based_cold_start",
            "context_match_score": len(samples) / max(len(context.get("samples", [])), 1),
            "data_quality_score": effective / max(len(samples), 1)}


def bo_parameter_recommendation_tool(context: dict[str, Any]) -> ParameterRecommendation:
    support = assess_data_support(context)
    parameters = []
    if support["support_status"] != "insufficient":
        for item in context.get("bo_candidates") or []:
            parameters.append(ParameterValue(**item, source_type="bo_recommendation",
                allowed_for_simple_trial=True, allowed_for_full_trial=True,
                allowed_for_formal_process=bool(item.get("historically_validated")), allowed_for_bo_prior=True))
    return ParameterRecommendation(recommendation_id=stable_id("rec-bo", str(context.get("task_id"))),
        recommendation_mode="bo_with_rag_prior" if context.get("approved_priors") else "bo",
        support_status=support["support_status"], authority_level="verified" if parameters else "none",
        intended_use=context.get("intended_use", "simple_trial"), parameters=parameters, data_support=support,
        warnings=[] if parameters else ["context-matched BO data are insufficient"])


def rag_parameter_recommendation_tool(context: dict[str, Any]) -> ParameterRecommendation:
    evidence = credibility_summary(context.get("rag_hits") or [], context.get("task_spec") or {})
    approved = [item for item in context.get("extracted_parameters") or [] if item.get("review_status") == "approved"]
    parameters = [ParameterValue(**{k: v for k, v in item.items() if k != "review_status"},
        source_type="rag_parameter_recommendation", allowed_for_simple_trial=True,
        allowed_for_full_trial=False, allowed_for_formal_process=False, allowed_for_bo_prior=True) for item in approved]
    support = "supported" if evidence["evidence_status"] == "sufficient" and parameters else \
        "partially_supported" if evidence["sources"] else "insufficient"
    return ParameterRecommendation(recommendation_id=stable_id("rec-rag", str(context.get("task_id"))),
        recommendation_mode="rag", support_status=support,
        authority_level="reviewed" if parameters else "none", intended_use=context.get("intended_use", "simple_trial"),
        parameters=parameters, context_match={"evidence": evidence}, requires_review=support != "supported",
        warnings=evidence["warnings"])


def llm_fallback_parameter_tool(context: dict[str, Any], generator: Callable[[dict], list[dict]]) -> ParameterRecommendation:
    if not all(context.get(key) for key in ("policy_authorized", "user_allows_exploration",
                                             "trial_allowed", "equipment_hard_bounds_complete")):
        raise PermissionError("LLM fallback is not authorized")
    parameters = [ParameterValue(**item, source_type="llm_fallback_hypothesis",
        allowed_for_simple_trial=True, allowed_for_full_trial=False,
        allowed_for_formal_process=False, allowed_for_bo_prior=False) for item in generator(context)]
    return ParameterRecommendation(recommendation_id=stable_id("rec-llm", str(context.get("task_id"))),
        recommendation_mode="llm_fallback", support_status="supported", authority_level="exploratory",
        intended_use="simple_trial", parameters=parameters, requires_review=True, requires_trial_validation=True,
        warnings=["exploratory hypothesis; user approval and trial validation required"])


def parameter_provenance_registry_tool(recommendation: ParameterRecommendation) -> list[dict[str, Any]]:
    records = [{"provenance_id": stable_id("provenance", recommendation.recommendation_id, item.name),
             "parameter_name": item.name, "value": item.value, "range": item.range, "unit": item.unit,
             "source_type": item.source_type, "recommendation_id": recommendation.recommendation_id,
             "source_refs": item.source_refs, "authority_level": recommendation.authority_level,
             "allowed_for_simple_trial": item.allowed_for_simple_trial,
             "allowed_for_full_trial": item.allowed_for_full_trial,
             "allowed_for_formal_process": item.allowed_for_formal_process,
             "allowed_for_bo_prior": item.allowed_for_bo_prior, "created_at": utc_now_iso()}
            for item in recommendation.parameters]
    init_database()
    with get_connection() as conn:
        for record in records:
            permissions = {key: record[key] for key in (
                "allowed_for_simple_trial", "allowed_for_full_trial",
                "allowed_for_formal_process", "allowed_for_bo_prior")}
            conn.execute("INSERT OR REPLACE INTO parameter_provenance VALUES (?,?,?,?,?,?,?,?,?,?)", (
                record["provenance_id"], record["recommendation_id"], record["parameter_name"],
                json.dumps({"value": record["value"], "range": record["range"]}, ensure_ascii=False),
                record["unit"], record["source_type"], json.dumps(record["source_refs"], ensure_ascii=False),
                record["authority_level"], json.dumps(permissions), record["created_at"]))
        conn.commit()
    return records


def _context_match(sample: dict[str, Any], context: dict[str, Any]) -> bool:
    task = context.get("task_spec") or {}
    return all(not task.get(key) or sample.get(key) == task.get(key)
               for key in ("material", "process_type", "equipment_revision", "fidelity_level"))
