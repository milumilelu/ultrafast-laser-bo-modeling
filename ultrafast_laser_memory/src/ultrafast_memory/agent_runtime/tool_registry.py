from __future__ import annotations

from pathlib import Path
from typing import Any

from ultrafast_agent.runtime import ToolContract, ToolRegistry
from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_domain.process import ParameterValue
from ultrafast_integrations.storage.read_models import list_bo_training_samples
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.equipment.bounds import (
    PARAMETER_UNITS,
    build_machine_bounds,
    safety_bounds_from_equipment,
)
from ultrafast_memory.ingestion.pipeline import ingest_file
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge as bootstrap_service
from ultrafast_memory.process_workflow.closure import bo_sample_eligibility, quality_decision
from ultrafast_memory.process_workflow.repository import ProcessWorkflowRepository
from ultrafast_memory.rag.parameter_recommendation import recommend_from_evidence
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.trial.service import TrialApplicationService


TOOL_REGISTRY_VERSION = "v32-llm-first-provenance-boundaries-1"


FOREGROUND_SAFE_TOOL_NAMES = {
    "get_equipment_context",
    "search_knowledge",
    "recommend_process_parameters",
    "manage_trial",
    "manage_process",
    "record_process_result",
}
CORE_TOOL_NAMES = tuple(sorted(FOREGROUND_SAFE_TOOL_NAMES))
ON_DEMAND_TOOL_NAMES = ("bootstrap_external_knowledge", "ingest_files", "generate_report")
BASE_TOOL_NAMES = set(FOREGROUND_SAFE_TOOL_NAMES)


def build_main_agent_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    contracts = (
        _contract("get_equipment_context", "Read authoritative fixed equipment conditions and tunable capabilities.", _equipment, default=True, cache="equipment_revision"),
        _contract(
            "search_knowledge",
            "Search purpose-governed internal evidence with review authority and citations.",
            _search,
            cache="turn",
        ),
        _contract(
            "recommend_process_parameters",
            "Apply the governed BO then reviewed-RAG policy without LLM-generated values.",
            _recommend_process_parameters,
            timeout=90_000,
            input_schema={"type": "object", "required": [
                "task_context", "process_plan", "variables", "equipment_context",
            ]},
        ),
        _contract("recommend_parameters_bo", "Compute provenance-bearing process setpoints from validated matching BO samples.", _recommend_bo, timeout=60_000, required=("equipment_snapshot.tunable_capabilities",)),
        _contract(
            "recommend_parameters_rag",
            "Extract and equipment-check a conservative candidate from reviewed RAG evidence.",
            _recommend_rag,
            input_schema={"type": "object", "required": [
                "task_context", "process_plan", "variables", "equipment_context",
            ]},
        ),
        _contract(
            "manage_trial",
            "Manage the trial lifecycle. create accepts operation, trial_mode, representative_geometry, "
            "measurement_plan, acceptance_criteria, and stop_conditions; numeric parameter candidates "
            "are copied only from the latest allowed_for_trial parameter Tool Observation.",
            _manage_trial,
            side="domain_write",
            input_schema={"type": "object", "required": ["operation"]},
        ),
        _contract(
            "manage_process",
            "Manage formal processing. Formal parameter values come only from an unlocked measured trial; "
            "Planner-supplied parameter values are ignored.",
            _manage_process,
            side="domain_write",
            input_schema={"type": "object", "required": ["operation"]},
        ),
        _contract("record_process_result", "Record supplied observations without inventing missing measurements.", _record_result, side="session_state_write"),
        _contract("bootstrap_external_knowledge", "Create review candidates from explicit external evidence.", _bootstrap, approval=True),
        _contract("ingest_files", "Ingest explicitly supplied supported files.", _ingest_files, side="artifact_write"),
        _contract("generate_report", "Generate a traceable task report as optional post-processing.", _generate_report, side="report_write"),
    )
    for contract in contracts:
        registry.register(contract)
    return registry


def _contract(name: str, purpose: str, handler: Any, *, timeout: int = 30_000,
              side: str = "none", approval: bool = False, default: bool = False,
              cache: str = "none", required: tuple[str, ...] = (),
              input_schema: dict[str, Any] | None = None) -> ToolContract:
    return ToolContract(
        name=name, purpose=purpose, handler=handler, timeout_ms=timeout,
        side_effect_level=side, requires_human_approval=approval,
        exposed_by_default=default, cache_policy=cache, requires_context=required,
        input_schema=input_schema or {},
    )


def _task(context: dict[str, Any]) -> dict[str, Any]:
    working = context.get("working_context") or {}
    return dict(working.get("task") or context.get("task_spec") or {})


def _legacy_task(
    context: dict[str, Any], task_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = dict(task_override or _task(context))
    material = task.get("material")
    geometry = task.get("geometry") or {}
    workpiece = task.get("workpiece") or {}
    return {
        **task,
        "material": material.get("name") if isinstance(material, dict) else material,
        "process_type": task.get("process_type") or task.get("process_intent")
        or task.get("task_type") or geometry.get("feature_type"),
        "objective": task.get("objective") or task.get("targets") or "process_quality",
        "thickness_mm": task.get("thickness_mm") or workpiece.get("thickness_mm")
        or geometry.get("workpiece_thickness_mm"),
    }


def _equipment(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    equipment = build_machine_bounds()
    return {
        "status": "success",
        "summary": "已分层读取设备固定条件与可调能力；可调范围只作为安全约束。",
        "active": equipment.get("active", False),
        "equipment_id": equipment.get("equipment_profile_id"),
        "equipment_profile_id": equipment.get("equipment_profile_id"),
        "profile_name": equipment.get("profile_name"),
        "revision": equipment.get("revision_id"),
        "revision_id": equipment.get("revision_id"),
        "fixed_conditions": dict(equipment.get("fixed_conditions") or {}),
        "tunable_capabilities": dict(equipment.get("tunable_capabilities") or {}),
        "missing_equipment_fields": list(equipment.get("missing_equipment_fields") or []),
    }


def _search(
    payload: dict[str, Any], context: dict[str, Any], *, _include_full_hits: bool = False,
) -> dict[str, Any]:
    task = _legacy_task(context)
    query = str(payload.get("query") or " ".join(
        str(task.get(key) or "") for key in ("material", "process_type", "objective")
    )).strip()
    if not query:
        return {"status": "insufficient_data", "summary": "缺少可检索的任务描述。", "missing": ["query_or_task_context"]}
    purpose = str(payload.get("purpose") or "literature_background")
    filters = dict(payload.get("filters") or {})
    if task.get("material"):
        filters.setdefault("material", task["material"])
    if task.get("process_type"):
        filters.setdefault("process_type", task["process_type"])
    result = query_rag({
        "query": query,
        "top_k": int(payload.get("top_k") or 8),
        "filters": filters,
        "purpose": purpose,
        "index_name": str(payload.get("index_name") or "literature_default"),
        "session_id": context.get("session_id"),
    })
    hits = list(result.get("hits") or [])
    evidence_pack = {key: value for key, value in result.items() if key != "hits"}
    authorities = sorted({str(hit.get("authority_level")) for hit in hits})
    observation_hits = hits if _include_full_hits else [
        {
            key: (
                str(hit.get(key) or "")[:240]
                if key in {"content", "text"}
                else hit.get(key)
            )
            for key in (
                "chunk_id", "paper_id", "title", "section_type", "authority_level",
                "score", "rerank_score", "content", "text",
            )
            if hit.get(key) is not None
        }
        for hit in hits[:3]
        if isinstance(hit, dict)
    ]
    return {"status": "success", "summary": "内部知识检索完成。", "query": query,
            "purpose": purpose, "evidence_pack": evidence_pack,
            "hit_count": len(hits), "hits": observation_hits,
            "provenance": [{"source_type": "rag_evidence", "authority_levels": authorities}]}


def _bootstrap(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return bootstrap_service(task_spec=_legacy_task(context), question=payload.get("question"),
                             query_intent=str(payload.get("query_intent") or "find_literature_prior"),
                             max_sources=int(payload.get("max_sources") or 5))


def _parameter_result(*, status: str, parameters: dict[str, Any], source_type: str,
                      source_refs: list[Any] | None = None, data_support: dict[str, Any] | None = None,
                      uncertainty: dict[str, Any] | None = None, limitations: list[str] | None = None,
                      evidence_level: str = "unknown", equipment: dict[str, Any] | None = None,
                      variables: list[str] | None = None, authority_level: str | None = None,
                      strategy_parameters: dict[str, Any] | None = None,
                      parameter_units: dict[str, str | None] | None = None,
                      parameter_details: dict[str, dict[str, Any]] | None = None,
                      validated: bool = False, allowed_for_trial: bool = True,
                      allowed_for_formal_process: bool = False,
                      allowed_for_bo_training: bool = False) -> dict[str, Any]:
    equipment = equipment or {}
    fixed = dict(equipment.get("fixed_conditions") or {})
    selected = list(dict.fromkeys(variables or list(parameters)))
    refs = [str(item) for item in (source_refs or [])]
    parameter_units = parameter_units or {}
    parameter_details = parameter_details or {}
    process_parameters: dict[str, dict[str, Any]] = {}
    for name in selected:
        if name in fixed or name not in parameters:
            continue
        value = parameters[name]
        if not isinstance(value, (int, float, str)):
            continue
        details = parameter_details.get(name) or {}
        parameter = ParameterValue(
            name=name,
            value=value,
            unit=details.get("unit") or PARAMETER_UNITS.get(name),
            role="process_setpoint",
            source_type=source_type,
            source_refs=[str(item) for item in details.get("source_refs") or refs],
            authority_level=str(
                details.get("authority_level") or authority_level or evidence_level
            ),
            uncertainty=dict(details.get("uncertainty") or uncertainty or {}),
            validated=validated,
            allowed_for_trial=allowed_for_trial,
            allowed_for_formal_process=allowed_for_formal_process,
            allowed_for_bo_training=allowed_for_bo_training,
        )
        process_parameters[name] = parameter.model_dump(mode="json")
    semantic_strategy_parameters: dict[str, dict[str, Any]] = {}
    for name, value in (strategy_parameters or {}).items():
        if not isinstance(value, (int, float, str)):
            continue
        details = parameter_details.get(name) or {}
        parameter = ParameterValue(
            name=name,
            value=value,
            unit=details.get("unit") or parameter_units.get(name) or PARAMETER_UNITS.get(name),
            role="strategy_parameter",
            source_type=source_type,
            source_refs=[str(item) for item in details.get("source_refs") or refs],
            authority_level=str(
                details.get("authority_level") or authority_level or evidence_level
            ),
            uncertainty=dict(details.get("uncertainty") or uncertainty or {}),
            validated=validated,
            allowed_for_trial=allowed_for_trial,
            allowed_for_formal_process=allowed_for_formal_process,
            allowed_for_bo_training=allowed_for_bo_training,
        )
        semantic_strategy_parameters[name] = parameter.model_dump(mode="json")
    return {
        "status": status,
        "fixed_equipment_conditions": fixed,
        "process_parameters": process_parameters,
        "strategy_parameters": semantic_strategy_parameters,
        "derived_metrics": {},
        "source_type": source_type,
        "source_refs": refs, "data_support": data_support or {},
        "evidence_level": evidence_level, "uncertainty": uncertainty or {},
        "authority_level": authority_level or evidence_level,
        "validated": validated,
        "allowed_for_trial": allowed_for_trial,
        "allowed_for_formal_process": allowed_for_formal_process,
        "allowed_for_bo_training": allowed_for_bo_training,
        "limitations": limitations or [],
        "recommended_use": (["trial"] if allowed_for_trial else [])
        + (["formal_process"] if allowed_for_formal_process else []),
        "provenance": [{"source_type": source_type, "source_refs": refs}],
    }


class RecommendationAuthorityPolicy:
    """Translate BO evidence into trial/formal authority without status inflation."""

    @staticmethod
    def assess(raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        mode = str(raw.get("model_status") or "blocked")
        readiness = raw.get("readiness_report") or {}
        metrics = readiness.get("validation_metrics") or {}
        matched = int(raw.get("sample_count") or 0)
        effective = int(readiness.get("complete_feature_count") or 0)
        uncertainty_calibrated = bool(readiness.get("uncertainty_calibrated"))
        model_validated = bool(metrics) and uncertainty_calibrated
        support = (
            "supported"
            if mode == "data_driven_bo" and raw.get("bo_invoked") and model_validated
            else "insufficient"
        )
        formal = support == "supported" and _verified_trial_unlocked(context)
        return {
            "support_status": support,
            "model_mode": mode,
            "matched_sample_count": matched,
            "effective_sample_count": effective,
            "context_match_score": 1.0 if matched else 0.0,
            "fidelity": "not_reported",
            "fidelity_level": "not_reported",
            "model_validation": metrics,
            "uncertainty_calibrated": uncertainty_calibrated,
            "validated": support == "supported",
            "allowed_for_trial": support != "insufficient",
            "allowed_for_formal_process": formal,
        }


def _recommend_bo(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    equipment = _normalize_equipment(
        payload.get("equipment_context") or _equipment_snapshot(context)
    )
    safety_bounds = safety_bounds_from_equipment(equipment)
    raw = LegacyBOCompatibilityAdapter().recommend(
        _legacy_task(context, payload.get("task_context")), list_bo_training_samples(),
        {**equipment, "machine_bounds": safety_bounds},
        payload.get("approved_priors") or [],
    )
    authority = RecommendationAuthorityPolicy.assess(raw, context)
    raw_parameters = raw.get("parameters") or raw.get("candidate") \
        or raw.get("recommended_parameters") or {}
    parameters = raw_parameters if authority["support_status"] == "supported" else {}
    status = (
        "success" if authority["support_status"] == "supported" else "insufficient_data"
    )
    return _parameter_result(
        status=status,
        parameters=parameters, source_type="bo",
        source_refs=list(raw.get("source_refs") or raw.get("sample_ids") or []),
        data_support=authority,
        uncertainty=raw.get("uncertainty") or {}, limitations=list(raw.get("limitations") or []),
        evidence_level=authority["support_status"],
        authority_level=f"bo_{authority['model_mode']}",
        equipment=equipment, variables=list(payload.get("variables") or parameters),
        validated=authority["validated"],
        allowed_for_trial=authority["allowed_for_trial"],
        allowed_for_formal_process=authority["allowed_for_formal_process"],
    )


def _recommend_process_parameters(
    payload: dict[str, Any], context: dict[str, Any],
) -> dict[str, Any]:
    """The sole foreground parameter entrypoint; ordering is not model-selectable."""
    payload, normalization = _normalize_parameter_request(payload, context)
    trace: list[dict[str, Any]] = []
    if normalization:
        trace.append({"step": "request_normalization", **normalization})
    bo = _recommend_bo(payload, context)
    bo_support = str((bo.get("data_support") or {}).get("support_status") or "insufficient")
    bo_mode = str((bo.get("data_support") or {}).get("model_mode") or "blocked")
    trace.append({
        "step": "bo_parameter_recommendation",
        "status": bo_support,
        "model_mode": bo_mode,
    })
    if bo_support == "supported":
        return _with_policy_trace(bo, trace, "bo")

    rag = _recommend_rag(payload, context)
    rag_usable = rag.get("status") == "success" and bool(rag.get("process_parameters"))
    trace.append({
        "step": "rag_parameter_recommendation",
        "status": "supported" if rag_usable else str(rag.get("status") or "insufficient_data"),
    })
    if rag_usable:
        return _with_policy_trace(rag, trace, "reviewed_rag")

    return {
        "status": "insufficient_data",
        "summary": "BO 与审核 RAG 均未提供有来源的可用候选；未生成任何 LLM 数值。",
        "process_parameters": {},
        "strategy_parameters": {},
        "allowed_for_trial": False,
        "allowed_for_formal_process": False,
        "internal_trace": trace,
        "policy_version": "bo-rag-no-invented-values-v1",
    }


def _normalize_parameter_request(
    payload: dict[str, Any], context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repair request structure only; never infer task-domain meaning."""
    normalized = dict(payload)
    normalized["task_context"] = dict(payload.get("task_context") or _task(context))
    equipment = _normalize_equipment(
        payload.get("equipment_context") or _equipment_snapshot(context)
    )
    normalized["equipment_context"] = equipment
    process_plan = dict(payload.get("process_plan") or {})
    declared = _declared_process_variable_roles(process_plan)
    requested = list(dict.fromkeys(
        str(name) for name in (payload.get("variables") or []) if str(name)
    ))
    tunable = set((equipment.get("tunable_capabilities") or {}).keys())
    dropped: list[str] = []
    injected: list[str] = []
    if declared:
        selected = [name for name in (requested or list(declared)) if name in declared]
        dropped = [name for name in requested if name not in declared]
    else:
        selected = [name for name in requested if name in tunable]
        dropped = [name for name in requested if name not in tunable]
        if selected:
            process_plan["controllable_variables"] = [
                {"name": name, "role": "process_setpoint"} for name in selected
            ]
            injected = list(selected)
    normalized["process_plan"] = process_plan
    normalized["variables"] = selected
    details = {
        "status": "normalized",
        "injected_process_setpoints": injected,
        "dropped_undeclared_variables": dropped,
    }
    return normalized, details if injected or dropped else {}


def _with_policy_trace(
    result: dict[str, Any], trace: list[dict[str, Any]], selected_source: str,
) -> dict[str, Any]:
    return {
        **result,
        "selected_source": selected_source,
        "internal_trace": trace,
        "policy_version": "bo-rag-no-invented-values-v1",
    }


def _verified_trial_unlocked(context: dict[str, Any]) -> bool:
    working = context.get("working_context") or {}
    for item in reversed(list(working.get("observations") or [])):
        data = item.get("data") if isinstance(item, dict) else None
        if not isinstance(data, dict):
            continue
        decision = data.get("formal_process_decision") or {}
        if decision.get("unlocked") is True or data.get("formal_process_unlocked") is True:
            return True
    return False


def _recommend_rag(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    process_plan = payload.get("process_plan") or {}
    variables = list(dict.fromkeys(map(str, payload.get("variables") or [])))
    roles = _declared_process_variable_roles(process_plan)
    invalid = [name for name in variables if name not in roles]
    if not variables or invalid:
        return {
            "status": "validation_error",
            "summary": "variables 必须由当前 ProcessPlan 明确选择。",
            "invalid_variables": invalid,
        }
    equipment = _normalize_equipment(
        payload.get("equipment_context") or _equipment_snapshot(context)
    )
    fixed = set((equipment.get("fixed_conditions") or {}).keys())
    if any(name in fixed for name in variables):
        return {
            "status": "validation_error",
            "summary": "设备固定条件不能作为 RAG 推荐变量。",
            "invalid_variables": [name for name in variables if name in fixed],
        }
    task = payload.get("task_context") or _task(context)
    material = task.get("material") if isinstance(task, dict) else None
    if isinstance(material, dict):
        material = material.get("name")
    process_type = None
    if isinstance(task, dict):
        geometry = task.get("geometry") or {}
        process_type = task.get("process_type") or task.get("process_intent") \
            or task.get("task_type") or geometry.get("feature_type")
    filters = dict(payload.get("filters") or {})
    if material:
        filters.setdefault("material", material)
    if process_type:
        filters.setdefault("process_type", process_type)
    query = str(payload.get("query") or " ".join(
        str(item or "") for item in (material, process_type, *variables)
    )).strip()
    evidence = _search(
        {
            **payload,
            "query": query,
            "filters": filters,
            "purpose": "parameter_recommendation",
        },
        context,
        _include_full_hits=True,
    )
    pack = evidence.get("evidence_pack") if isinstance(evidence.get("evidence_pack"), dict) else {}
    if pack.get("evidence_status") != "sufficient":
        empty_recommendation = {"missing_variables": variables}
        return _parameter_result(
            status="insufficient_data",
            parameters={},
            source_type="reviewed_rag",
            data_support=_rag_parameter_support_summary(evidence, empty_recommendation),
            limitations=[
                "当前 Evidence Pack 未达到参数用途的 sufficient 条件，未抽取或聚合数值。",
                "候选、用途不匹配或条件不匹配的命中不能生成试切参数。",
            ],
            evidence_level=str(pack.get("evidence_status") or "insufficient"),
            authority_level="insufficient_reviewed_evidence",
            equipment=equipment,
            variables=variables,
            allowed_for_trial=False,
        ) | {"missing_variables": variables}
    hits = list(evidence.get("hits") or [])
    recommendation = recommend_from_evidence(
        variables,
        {name: _canonical_parameter_role(roles[name]) for name in variables},
        hits,
        safety_bounds_from_equipment(equipment),
    )
    details = recommendation["parameter_details"]
    refs = list(dict.fromkeys(
        str(ref)
        for item in details.values()
        for ref in item.get("source_refs") or []
    ))
    if recommendation["missing_variables"]:
        return _parameter_result(
            status="insufficient_data",
            parameters={},
            source_type="reviewed_rag",
            source_refs=refs,
            data_support=_rag_parameter_support_summary(evidence, recommendation),
            limitations=[
                "审核证据未覆盖全部当前变量，未生成可执行参数候选。",
                "不得用调用者预填值补齐缺失证据。",
            ],
            evidence_level="insufficient_reviewed_evidence",
            authority_level="literature_prior",
            equipment=equipment,
            variables=variables,
            allowed_for_trial=False,
        ) | {"missing_variables": recommendation["missing_variables"]}
    return _parameter_result(
        status="success",
        parameters=recommendation["process_parameters"],
        strategy_parameters=recommendation["strategy_parameters"],
        parameter_details=details,
        source_type="reviewed_rag",
        source_refs=refs,
        data_support=_rag_parameter_support_summary(evidence, recommendation),
        limitations=["基于审核文献先验，仅允许试切；不代表全局最优或正式工艺。"],
        evidence_level="reviewed_evidence",
        authority_level="literature_prior",
        equipment=equipment,
        variables=variables,
        validated=False,
        allowed_for_trial=True,
        allowed_for_formal_process=False,
        allowed_for_bo_training=False,
    )


def _rag_parameter_support_summary(
    evidence: dict[str, Any], recommendation: dict[str, Any],
) -> dict[str, Any]:
    pack = evidence.get("evidence_pack") if isinstance(evidence.get("evidence_pack"), dict) else {}
    hits = list(evidence.get("hits") or [])
    metadata = pack.get("retrieval_metadata") if isinstance(pack.get("retrieval_metadata"), dict) else {}
    return {
        "support_status": pack.get("evidence_status") or "insufficient",
        "hit_count": len(hits),
        "authority_levels": sorted({
            str(hit.get("authority_level") or "unknown")
            for hit in hits if isinstance(hit, dict)
        }),
        "source_refs": sorted({
            str(hit.get("chunk_id")) for hit in hits
            if isinstance(hit, dict) and hit.get("chunk_id")
        }),
        "missing_evidence": list(pack.get("missing_evidence") or []),
        "missing_variables": list(recommendation.get("missing_variables") or []),
        "degraded": bool(metadata.get("degraded")),
        "fallback": metadata.get("fallback"),
    }


def _declared_process_variable_roles(process_plan: dict[str, Any]) -> dict[str, str]:
    """Read explicit declarations without requiring one fixed ProcessPlan layout."""
    found: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "controllable_variables":
                    items = child if isinstance(child, list) else [child]
                    for item in items:
                        name = item.get("name") if isinstance(item, dict) else item
                        if isinstance(name, str) and name:
                            role = item.get("role") if isinstance(item, dict) else None
                            found[name] = str(role or "process_setpoint")
                else:
                    visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(process_plan)
    return found


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


def _equipment_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    return _normalize_equipment(context.get("equipment_snapshot") or build_machine_bounds())


def _normalize_equipment(equipment: dict[str, Any]) -> dict[str, Any]:
    provided_tunable = equipment.get("tunable_capabilities")
    if isinstance(provided_tunable, dict):
        fixed = dict(equipment.get("fixed_conditions") or {})
        normalized_tunable: dict[str, dict[str, Any]] = {}
        for name, capability in provided_tunable.items():
            if not isinstance(capability, dict):
                continue
            normalized_tunable[name] = {
                **capability,
                "unit": capability.get("unit") or PARAMETER_UNITS.get(name),
                "role": capability.get("role") or "equipment_tunable",
            }
        for name in ("wavelength_nm", "spot_diameter_um", "pulse_width_fs"):
            value = equipment.get(name)
            if name not in normalized_tunable and isinstance(value, (int, float)):
                fixed.setdefault(name, value)
        return {
            **equipment,
            "fixed_conditions": fixed,
            "tunable_capabilities": normalized_tunable,
        }
    raw = equipment.get("machine_bounds") or {}
    fixed: dict[str, Any] = {}
    tunable: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        if value[0] == value[1]:
            fixed[name] = value[0]
        else:
            tunable[name] = {
                "min": value[0], "max": value[1],
                "unit": PARAMETER_UNITS.get(name), "role": "equipment_tunable",
            }
    return {**equipment, "fixed_conditions": fixed, "tunable_capabilities": tunable}


def _manage_trial(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    service = TrialApplicationService()
    operation = str(payload.get("operation") or "get")
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    if operation == "create":
        if isinstance(payload.get("trial"), dict):
            return {
                "status": "validation_error",
                "summary": (
                    "manage_trial 不接受嵌套 trial 或未经参数 Tool 审核的自造数值。"
                    "请先通过 recommend_process_parameters 形成 allowed_for_trial 候选。"
                ),
                "invalid_fields": ["trial"],
            }
        approved_candidates = _approved_trial_candidates_from_observations(context)
        if not approved_candidates:
            return {
                "status": "insufficient_data",
                "summary": (
                    "尚无 allowed_for_trial 参数 Observation，未创建空试切计划。"
                    "请补充审核证据或合格历史/实验数据后重新调用 recommend_process_parameters。"
                ),
                "required_observation": "recommend_process_parameters.allowed_for_trial",
            }
        plan_definition = payload.get("plan_definition") \
            if isinstance(payload.get("plan_definition"), dict) else {
                key: payload.get(key)
                for key in (
                    "representative_geometry", "measurement_plan",
                    "acceptance_criteria", "stop_conditions",
                )
                if payload.get(key) is not None
            }
        missing_design = [
            key for key in ("representative_geometry", "measurement_plan")
            if not plan_definition.get(key)
        ]
        if missing_design:
            return {
                "status": "insufficient_data",
                "summary": (
                    "试切语义设计不完整；Tool 不再按工艺关键词套用固定几何或通用检测模板。"
                    "请由 Main LLM 根据当前任务补充代表性几何和测量方案。"
                ),
                "missing": missing_design,
            }
        equipment = _equipment_snapshot(context)
        result = service.create_plan(task_id, {
            **payload, "trial_mode": payload.get("trial_mode") or "simple_trial_cut",
            "task_spec": _legacy_task(context),
            "machine_bounds": safety_bounds_from_equipment(equipment),
            "approved_parameter_candidates": approved_candidates,
            "plan_definition": plan_definition,
        })
    elif operation == "get":
        result = service.get_plan(str(payload["trial_plan_id"]))
    elif operation == "start":
        if not context.get("human_approved"):
            return {"status": "blocked", "summary": "开始真实试切需要本次明确确认。", "required": "scoped_user_approval"}
        plan = service.get_plan(str(payload["trial_plan_id"]))
        matrix = list(plan.get("parameter_matrix") or [])
        try:
            candidate_index = int(payload.get("candidate_index") or 0)
            approved_parameters = matrix[candidate_index]
        except (IndexError, TypeError, ValueError):
            return {
                "status": "validation_error",
                "summary": "试切方案中没有对应的已审核参数候选，未启动执行。",
                "invalid_field": "candidate_index",
            }
        result = service.start_execution(str(payload["trial_plan_id"]), {
            **payload,
            "actual_parameters": dict(approved_parameters),
        })
    elif operation == "record_result":
        result = service.create_result(str(payload["execution_id"]), payload)
    elif operation == "evaluate":
        result = service.evaluate(str(payload["result_id"]), payload)
    elif operation == "close":
        result = {"trial_plan_id": payload.get("trial_plan_id"), "closed": True,
                  "reason": payload.get("reason") or "agent_decision"}
    else:
        return {"status": "validation_error", "summary": f"不支持的试切操作：{operation}"}
    warnings = list(result.get("warnings") or []) if isinstance(result, dict) else []
    if payload.get("iteration") and payload.get("recommended_budget") and int(payload["iteration"]) >= int(payload["recommended_budget"]):
        warnings.append("已达到建议试切预算；这是规划提示，不会强制终止任务。")
    return {"status": "success", "summary": f"试切操作 {operation} 已完成。", "result": result, "warnings": warnings}


def _approved_trial_candidates_from_observations(
    context: dict[str, Any],
) -> list[dict[str, float | int | str]]:
    working = context.get("working_context") or {}
    for observation in reversed(list(working.get("observations") or [])):
        if not isinstance(observation, dict):
            continue
        meta = observation.get("meta") if isinstance(observation.get("meta"), dict) else {}
        tool_name = str(observation.get("tool_name") or meta.get("tool_name") or "")
        if tool_name != "recommend_process_parameters":
            continue
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        if data.get("allowed_for_trial") is not True:
            return []
        candidate: dict[str, float | int | str] = {}
        for group in ("process_parameters", "strategy_parameters"):
            parameters = data.get(group) if isinstance(data.get(group), dict) else {}
            for name, parameter in parameters.items():
                value = parameter.get("value") if isinstance(parameter, dict) else parameter
                if isinstance(value, (int, float, str)):
                    candidate[str(name)] = value
        return [candidate] if candidate else []
    return []


def _approved_formal_window_from_observations(
    context: dict[str, Any], trial_result_id: str | None,
) -> dict[str, Any]:
    working = context.get("working_context") or {}
    for observation in reversed(list(working.get("observations") or [])):
        if not isinstance(observation, dict):
            continue
        meta = observation.get("meta") if isinstance(observation.get("meta"), dict) else {}
        tool_name = str(observation.get("tool_name") or meta.get("tool_name") or "")
        data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        decision = result.get("formal_process_decision") \
            if isinstance(result.get("formal_process_decision"), dict) else {}
        if tool_name != "manage_trial" or decision.get("unlocked") is not True:
            continue
        observed_result_id = str(result.get("result_id") or "")
        if trial_result_id and observed_result_id != trial_result_id:
            continue
        try:
            service = TrialApplicationService()
            trial_result = service.repository.get_result(observed_result_id)
            execution = service.repository.get_execution(str(trial_result["execution_id"]))
        except Exception:  # noqa: BLE001 - missing persisted trial evidence means no release
            return {}
        actual = execution.get("actual_parameters")
        return dict(actual) if isinstance(actual, dict) else {}
    return {}


def _manage_process(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    repo = ProcessWorkflowRepository()
    operation = str(payload.get("operation") or "prepare")
    now = utc_now_iso()
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    equipment = context.get("equipment_snapshot") or build_machine_bounds()
    if operation == "prepare":
        trial_result_id = str(payload.get("trial_result_id") or "")
        approved_window = _approved_formal_window_from_observations(
            context, trial_result_id or None,
        )
        if not approved_window:
            return {
                "status": "insufficient_data",
                "summary": (
                    "没有已通过测量并解锁正式加工的试切参数；未接受 Planner 提供的参数值。"
                ),
                "required_observation": "manage_trial.evaluate.formal_process_decision.unlocked",
            }
        plan = {
            "plan_id": str(payload.get("plan_id") or stable_id("fplan", task_id, now)),
            "task_id": task_id, "trial_result_id": payload.get("trial_result_id"),
            "parameter_recommendation_id": payload.get("parameter_recommendation_id"),
            "equipment_revision": str(payload.get("equipment_revision") or equipment.get("revision_id") or "unknown"),
            "approved_window": approved_window,
            "toolpath": payload.get("toolpath") or {}, "monitoring_plan": payload.get("monitoring_plan") or {},
            "stop_conditions": payload.get("stop_conditions") or [], "release_status": "prepared", "created_at": now,
        }
        return {"status": "success", "summary": "正式加工方案已准备，尚未启动设备。", "result": repo.save_plan(plan)}
    if operation == "start":
        if not context.get("human_approved"):
            return {"status": "blocked", "summary": "开始真实正式加工需要本次明确确认。", "required": "scoped_user_approval"}
        plan_id = str(payload["plan_id"])
        plan = repo.get_plan(plan_id)
        if not plan:
            return {"status": "validation_error", "summary": "未找到正式加工方案。"}
        execution = {
            "execution_id": str(payload.get("execution_id") or stable_id("fexec", plan_id, now)),
            "plan_id": plan_id, "actual_parameters": plan.get("approved_window") or {},
            "actual_path": payload.get("actual_path") or plan.get("toolpath") or {},
            "runtime_log": {"checkpoints": []}, "started_at": now, "finished_at": None, "status": "running",
        }
        repo.set_plan_status(plan_id, "released")
        return {"status": "success", "summary": "已记录本次确认并启动正式加工执行。", "result": repo.save_execution(execution)}
    if operation == "record_checkpoint":
        execution = repo.get_execution(str(payload["execution_id"]))
        if not execution:
            return {"status": "validation_error", "summary": "未找到正式加工执行记录。"}
        observation = payload.get("observation") or {k: v for k, v in payload.items() if k not in {"operation", "execution_id"}}
        unsafe = bool(payload.get("unsafe") or payload.get("equipment_alarm"))
        checkpoint = {
            "checkpoint_id": str(payload.get("checkpoint_id") or stable_id("checkpoint", execution["execution_id"], now)),
            "execution_id": execution["execution_id"], "checkpoint_type": str(payload.get("checkpoint_type") or "progress"),
            "progress_percent": payload.get("progress_percent"), "observation": observation,
            "decision": "pause_for_safety" if unsafe else str(payload.get("decision") or "agent_review_required"), "created_at": now,
        }
        repo.save_checkpoint(checkpoint)
        return {"status": "blocked" if unsafe else "success",
                "summary": "检测到明确安全信号，已建议暂停。" if unsafe else "加工 checkpoint 已记录，主 Agent 可自由调整、继续或回退试切。",
                "result": checkpoint}
    if operation == "record_result":
        execution_id = str(payload["execution_id"])
        measurements = payload.get("measurements") or {}
        required = list(payload.get("required_metrics") or [])
        constraints = dict(payload.get("constraint_results") or {})
        decision = quality_decision(required, measurements, constraints)
        inspection = {
            "inspection_id": str(payload.get("inspection_id") or stable_id("inspection", execution_id, now)),
            "execution_id": execution_id, "measurement_plan": {"required_metrics": required},
            "measurements": measurements, "defects": payload.get("defects") or [], "files": payload.get("files") or [],
            "completeness_status": "INCOMPLETE_DATA" if decision["missing_metrics"] else "complete", "created_at": now,
        }
        repo.save_inspection(inspection)
        public_decision = "INCOMPLETE_DATA" if decision["missing_metrics"] else ("FAIL" if decision["failed_metrics"] else "PASS")
        quality = {
            "quality_decision_id": stable_id("quality", inspection["inspection_id"], now),
            "inspection_id": inspection["inspection_id"], "decision": public_decision,
            "passed_metrics": decision["passed_metrics"], "failed_metrics": decision["failed_metrics"],
            "missing_metrics": decision["missing_metrics"], "basis": constraints,
            "reviewer_comment": payload.get("reviewer_comment"), "created_at": now,
        }
        repo.save_quality_decision(quality)
        return {"status": "insufficient_data" if public_decision == "INCOMPLETE_DATA" else "success",
                "summary": "检测数据不完整，需要补充测量；未判定为失败。" if public_decision == "INCOMPLETE_DATA" else f"质量评价：{public_decision}。",
                "result": {"inspection": inspection, "quality": quality}}
    if operation in {"complete", "abort"}:
        execution = repo.get_execution(str(payload["execution_id"]))
        if not execution:
            return {"status": "validation_error", "summary": "未找到正式加工执行记录。"}
        execution.update({"status": "completed" if operation == "complete" else "aborted", "finished_at": now})
        return {"status": "success", "summary": f"正式加工已{('完成' if operation == 'complete' else '中止')}。", "result": repo.update_execution(execution)}
    return {"status": "validation_error", "summary": f"不支持的正式加工操作：{operation}"}


def _record_result(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict) or not measurements:
        return {"status": "insufficient_data", "summary": "缺少实测结果，未判定加工失败。", "missing": ["measurements"]}
    session_id = str(context["session_id"])
    record = {"task_id": payload.get("task_id") or session_id, "parameters": payload.get("parameters") or {},
              "measurements": measurements, "defects": payload.get("defects") or [],
              "attachments": payload.get("attachments") or [], "recorded_at": utc_now_iso()}
    warnings: list[str] = []
    count = 0
    try:
        state = get_session_state(session_id)
        observations = list(state.get("agent_observations_json") or [])
        observations.append(record)
        update_session_state(session_id, {"agent_observations_json": observations[-100:]})
        count = len(observations)
    except Exception as exc:  # noqa: BLE001 - front task outranks archival persistence
        warnings.append(f"结果持久化失败：{type(exc).__name__}")
    eligibility = bo_sample_eligibility({**record, "validation_status": payload.get("validation_status")})
    return {"status": "partial" if warnings else "success", "summary": "加工结果已形成前台 Observation。",
            "recorded": record, "observation_count": count, "bo_data_eligibility": eligibility,
            "warnings": warnings}


def _generate_report(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    return TaskReportService().generate(task_id, {**payload, "task_spec": _legacy_task(context),
                                                   "equipment_snapshot": context.get("equipment_snapshot") or {}},
                                        payload.get("run_id"))


def _ingest_files(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not paths:
        return {"status": "insufficient_data", "missing": ["paths"]}
    return {"status": "success", "files": [{"path": str(Path(path)), **ingest_file(path)} for path in paths]}
