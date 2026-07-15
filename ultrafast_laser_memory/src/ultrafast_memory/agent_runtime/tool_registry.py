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


TOOL_REGISTRY_VERSION = "v31-foreground-tools-1"


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
            "Apply the governed BO, reviewed-RAG, then controlled-exploration policy.",
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
            "propose_exploratory_parameters",
            "Safety-check a Main-Agent exploratory hypothesis for selected ProcessPlan variables.",
            _exploratory,
            input_schema={"type": "object", "required": [
                "task_context", "process_plan", "variables", "equipment_context",
                "evidence_summary", "intended_use", "candidate",
            ], "properties": {
                "variables": {"type": "array", "items": {"type": "string"}},
                "intended_use": {"type": "string", "enum": ["trial"]},
                "candidate": {"type": "object"},
            }},
        ),
        _contract("manage_trial", "Create, read, start, record, evaluate, or close the single trial lifecycle.", _manage_trial, side="domain_write"),
        _contract("manage_process", "Prepare, start, checkpoint, record, complete, or abort formal processing.", _manage_process, side="domain_write"),
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


def _legacy_task(context: dict[str, Any]) -> dict[str, Any]:
    task = _task(context)
    material = task.get("material")
    geometry = task.get("geometry") or {}
    workpiece = task.get("workpiece") or {}
    return {
        **task,
        "material": material.get("name") if isinstance(material, dict) else material,
        "process_type": task.get("process_type") or task.get("process_intent"),
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


def _search(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task = _legacy_task(context)
    query = str(payload.get("query") or " ".join(
        str(task.get(key) or "") for key in ("material", "process_type", "objective")
    )).strip()
    if not query:
        return {"status": "insufficient_data", "summary": "缺少可检索的任务描述。", "missing": ["query_or_task_context"]}
    purpose = str(payload.get("purpose") or "literature_background")
    result = query_rag({
        "query": query,
        "top_k": int(payload.get("top_k") or 8),
        "filters": dict(payload.get("filters") or {}),
        "purpose": purpose,
        "index_name": str(payload.get("index_name") or "literature_default"),
        "session_id": context.get("session_id"),
    })
    authorities = sorted({str(hit.get("authority_level")) for hit in result.get("hits") or []})
    return {"status": "success", "summary": "内部知识检索完成。", "query": query,
            "purpose": purpose, "result": result,
            "hits": result.get("hits") or [],
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
        if mode == "data_driven_bo" and raw.get("bo_invoked") and model_validated:
            support = "supported"
        elif mode in {"data_driven_bo", "hybrid_rule_bo", "rule_based_cold_start"}:
            support = "partially_supported"
        else:
            support = "insufficient"
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
    equipment = _equipment_snapshot(context)
    safety_bounds = safety_bounds_from_equipment(equipment)
    raw = LegacyBOCompatibilityAdapter().recommend(
        _legacy_task(context), list_bo_training_samples(),
        {**equipment, "machine_bounds": safety_bounds},
        payload.get("approved_priors") or [],
    )
    authority = RecommendationAuthorityPolicy.assess(raw, context)
    parameters = raw.get("parameters") or raw.get("candidate") or raw.get("recommended_parameters") or {}
    status = (
        "success" if authority["support_status"] == "supported"
        else "partial_support" if parameters and authority["support_status"] == "partially_supported"
        else "insufficient_data"
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
    ) | {"raw_result": raw}


def _recommend_process_parameters(
    payload: dict[str, Any], context: dict[str, Any],
) -> dict[str, Any]:
    """The sole foreground parameter entrypoint; ordering is not model-selectable."""
    trace: list[dict[str, Any]] = []
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
    if bo_mode == "hybrid_rule_bo" and bo.get("process_parameters"):
        result = dict(bo)
        if rag_usable:
            result.setdefault("limitations", []).append(
                "RAG 证据已检查，但未作为 BO 先验注入：只有经治理批准的 prior 才能改变 BO 搜索域。"
            )
            result["rag_prior_evidence"] = {
                "source_refs": rag.get("source_refs") or [],
                "authority_level": rag.get("authority_level"),
            }
        return _with_policy_trace(result, trace, "bo")
    if rag_usable:
        return _with_policy_trace(rag, trace, "reviewed_rag")
    if bo.get("process_parameters") and bo.get("allowed_for_trial"):
        return _with_policy_trace(bo, trace, "bo_cold_start")

    allow_fallback = bool(payload.get("allow_llm_fallback"))
    candidate = payload.get("candidate")
    if allow_fallback and isinstance(candidate, dict) and candidate:
        exploratory = _exploratory({**payload, "intended_use": "trial"}, context)
        trace.append({
            "step": "llm_fallback_parameter",
            "status": str(exploratory.get("status") or "validation_error"),
        })
        return _with_policy_trace(exploratory, trace, "llm_exploration")
    trace.append({
        "step": "llm_fallback_parameter",
        "status": "not_called",
        "reason": "fallback_not_enabled_or_candidate_missing",
    })
    return {
        "status": "insufficient_data",
        "summary": "BO 与审核 RAG 均未提供可用候选；未满足受控探索条件。",
        "process_parameters": {},
        "strategy_parameters": {},
        "allowed_for_trial": False,
        "allowed_for_formal_process": False,
        "internal_trace": trace,
        "policy_version": "bo-rag-exploration-v1",
    }


def _with_policy_trace(
    result: dict[str, Any], trace: list[dict[str, Any]], selected_source: str,
) -> dict[str, Any]:
    return {
        **result,
        "selected_source": selected_source,
        "internal_trace": trace,
        "policy_version": "bo-rag-exploration-v1",
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
        process_type = task.get("process_type") or task.get("process_intent")
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
    )
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
            data_support={"evidence": evidence, "extraction": recommendation},
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
        data_support={"evidence": evidence, "extraction": recommendation},
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


def _exploratory(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    intended_use = str(payload.get("intended_use") or "").strip().lower()
    if intended_use not in {"trial", "first_trial", "trial_cut", "simple_trial_cut", "试切"}:
        return {"status": "validation_error", "summary": "探索参数只允许 intended_use=trial。"}
    process_plan = payload.get("process_plan") or {}
    selected = list(dict.fromkeys(map(str, payload.get("variables") or [])))
    plan_variable_roles = _declared_process_variable_roles(process_plan)
    plan_variables = set(plan_variable_roles)
    if not selected or any(name not in plan_variables for name in selected):
        return {
            "status": "validation_error",
            "summary": "variables 必须由当前 ProcessPlan 明确选择。",
            "invalid_variables": [name for name in selected if name not in plan_variables],
        }
    equipment = _normalize_equipment(payload.get("equipment_context") or _equipment_snapshot(context))
    fixed = set((equipment.get("fixed_conditions") or {}).keys())
    if any(name in fixed for name in selected):
        return {
            "status": "validation_error",
            "summary": "设备固定条件不能作为探索性工艺变量。",
            "invalid_variables": [name for name in selected if name in fixed],
        }
    process_fixed = process_plan.get("fixed_conditions") or {}
    tunable = set((equipment.get("tunable_capabilities") or {}).keys())
    unvalidated_fixed_setpoints = sorted(
        name for name in process_fixed if name in tunable and name not in selected
    )
    if unvalidated_fixed_setpoints:
        return {
            "status": "validation_error",
            "summary": "ProcessPlan 把设备可调量写成固定值但未验证："
            f"{', '.join(unvalidated_fixed_setpoints)}。请将其作为 process_setpoint 加入 "
            "variables/candidate，或从 fixed_conditions 删除；设备 min/max 不是固定值。",
            "invalid_variables": unvalidated_fixed_setpoints,
        }
    raw_candidate = payload.get("candidate") or {}
    if not isinstance(raw_candidate, dict):
        return {
            "status": "validation_error",
            "summary": "candidate 必须是参数名到数值的 JSON 对象。",
            "received_type": type(raw_candidate).__name__,
        }
    wrapped_parameters = raw_candidate.get("parameters")
    if isinstance(wrapped_parameters, dict):
        raw_candidate = wrapped_parameters
    bounds = safety_bounds_from_equipment(equipment)
    candidate: dict[str, float | int] = {}
    strategy_candidate: dict[str, float | int | str] = {}
    parameter_units: dict[str, str | None] = {}
    adjustments: list[dict[str, Any]] = []
    for name in selected:
        raw_value = raw_candidate.get(name)
        value = raw_value.get("value") if isinstance(raw_value, dict) else raw_value
        role = _canonical_parameter_role(plan_variable_roles[name])
        if role == "strategy_parameter":
            if not isinstance(value, (int, float, str)):
                return {"status": "validation_error", "summary": f"探索候选缺少标量策略参数：{name}"}
            strategy_candidate[name] = value
            if isinstance(raw_value, dict) and isinstance(raw_value.get("unit"), str):
                parameter_units[name] = raw_value["unit"]
            continue
        if role != "process_setpoint":
            return {
                "status": "validation_error",
                "summary": f"探索变量角色不受支持：{name}={role}",
                "allowed_roles": ["process_setpoint", "strategy_parameter"],
            }
        if name not in bounds:
            return {
                "status": "validation_error",
                "summary": f"设备没有可调能力：{name}；若它决定加工方式而非设备设定值，"
                "请在 ProcessPlan 中显式声明 role=strategy_parameter。",
            }
        if not isinstance(value, (int, float)):
            return {"status": "validation_error", "summary": f"探索候选缺少数值参数：{name}"}
        lower, upper = float(bounds[name][0]), float(bounds[name][1])
        clipped = min(max(float(value), lower), upper)
        candidate[name] = int(round(clipped)) if name == "passes" else clipped
        if clipped != float(value):
            adjustments.append({"name": name, "original": value, "clipped": clipped, "bounds": [lower, upper]})
    result = _parameter_result(
        status="exploratory", parameters=candidate, source_type="llm_exploration",
        data_support={
            "task_context": payload.get("task_context") or {},
            "process_plan": process_plan,
            "evidence_summary": payload.get("evidence_summary") or {},
            "safety_bounds_used": {name: bounds[name] for name in candidate},
        },
        evidence_level="hypothesis", authority_level="exploratory",
        equipment=equipment, variables=selected, validated=False,
        strategy_parameters=strategy_candidate, parameter_units=parameter_units,
        allowed_for_trial=True, allowed_for_formal_process=False,
        allowed_for_bo_training=False,
        limitations=["仅用于第一轮试切；未经验证，不得直接用于正式加工或 BO 训练。"],
    )
    result["summary"] = "Main Agent 探索假设已通过设备边界安全检查。"
    result["safety_adjustments"] = adjustments
    return result


def _declared_process_variable_roles(process_plan: dict[str, Any]) -> dict[str, str]:
    """Read explicit declarations without requiring one fixed ProcessPlan layout."""
    found: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"controllable_variables", "selected_exploratory_variables"}:
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
        equipment = _equipment_snapshot(context)
        result = service.create_plan(task_id, {
            **payload, "trial_mode": payload.get("trial_mode") or "simple_trial_cut",
            "task_spec": _legacy_task(context),
            "machine_bounds": safety_bounds_from_equipment(equipment),
        })
    elif operation == "get":
        result = service.get_plan(str(payload["trial_plan_id"]))
    elif operation == "start":
        if not context.get("human_approved"):
            return {"status": "blocked", "summary": "开始真实试切需要本次明确确认。", "required": "scoped_user_approval"}
        result = service.start_execution(str(payload["trial_plan_id"]), payload)
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


def _manage_process(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    repo = ProcessWorkflowRepository()
    operation = str(payload.get("operation") or "prepare")
    now = utc_now_iso()
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    equipment = context.get("equipment_snapshot") or build_machine_bounds()
    if operation == "prepare":
        plan = {
            "plan_id": str(payload.get("plan_id") or stable_id("fplan", task_id, now)),
            "task_id": task_id, "trial_result_id": payload.get("trial_result_id"),
            "parameter_recommendation_id": payload.get("parameter_recommendation_id"),
            "equipment_revision": str(payload.get("equipment_revision") or equipment.get("revision_id") or "unknown"),
            "approved_window": payload.get("approved_window") or payload.get("parameters") or {},
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
            "plan_id": plan_id, "actual_parameters": payload.get("actual_parameters") or plan.get("approved_window") or {},
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
