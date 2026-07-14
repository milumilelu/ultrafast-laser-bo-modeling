from __future__ import annotations

# This is the authoritative registry used by the capability-discovery runtime.

from pathlib import Path
from typing import Any

from ultrafast_agent.runtime import ToolContract, ToolRegistry
from ultrafast_agent.task_intake import update_task_context_contract
from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_integrations.storage.read_models import list_bo_training_samples
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.ingestion.pipeline import ingest_file
from ultrafast_memory.knowledge_bootstrap.candidate_builder import build_knowledge_candidate
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge as bootstrap_service
from ultrafast_memory.knowledge_bootstrap.source_registry import register_external_source
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest
from ultrafast_memory.knowledge_review.service import apply_action
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.trial.service import TrialApplicationService


CORE_TOOL_NAMES = (
    "update_task_context",
    "get_equipment_context",
    "search_knowledge",
    "bootstrap_external_knowledge",
    "recommend_parameters_bo",
    "recommend_parameters_rag",
    "propose_exploratory_parameters",
    "manage_trial",
    "run_bo_iteration",
    "record_process_result",
    "create_knowledge_candidate",
    "generate_report",
)
ON_DEMAND_TOOL_NAMES = ("ingest_files", "review_knowledge_candidate")
BASE_TOOL_NAMES = {"update_task_context", "get_equipment_context"}


def build_main_agent_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(update_task_context_contract())
    contracts = (
        _contract("get_equipment_context", "Read the authoritative equipment revision and machine bounds.", _equipment, default=True),
        _contract("search_knowledge", "Search reviewed internal knowledge with traceable evidence.", _search),
        _contract("bootstrap_external_knowledge", "Create review candidates from external evidence after explicit user approval.", _bootstrap, approval=True),
        _contract("recommend_parameters_bo", "Recommend bounded parameters from context-matched validated BO samples.", _recommend_bo, required=("task_spec.material", "task_spec.process_type", "task_spec.objective", "equipment_snapshot.machine_bounds"), timeout=60_000),
        _contract("recommend_parameters_rag", "Retrieve reviewed evidence for a conservative parameter recommendation.", _recommend_rag, required=("task_spec.material", "task_spec.process_type")),
        _contract("propose_exploratory_parameters", "Propose explicitly non-optimal exploratory parameters inside equipment bounds.", _exploratory, required=("equipment_snapshot.machine_bounds",)),
        _contract("manage_trial", "Assess, plan, read, execute, record, or evaluate a trial through one application boundary.", _manage_trial, side="domain_write"),
        _contract("run_bo_iteration", "Run one bounded recommendation iteration and return an auditable candidate observation.", _bo_iteration, required=("task_spec.material", "task_spec.process_type", "equipment_snapshot.machine_bounds"), timeout=60_000),
        _contract("record_process_result", "Record supplied process measurements as an observation; never invent missing values.", _record_result, side="session_state_write"),
        _contract("create_knowledge_candidate", "Create a pending-review knowledge candidate from an explicit claim and source.", _create_candidate, side="knowledge_candidate_write"),
        _contract("generate_report", "Generate traceable Markdown and JSON task reports.", _generate_report, side="report_write"),
        _contract("ingest_files", "Ingest explicitly supplied supported process files.", _ingest_files, side="artifact_write"),
        _contract("review_knowledge_candidate", "Apply an explicit human review action to a knowledge candidate.", _review_candidate, side="knowledge_review_write", approval=True),
    )
    for contract in contracts:
        registry.register(contract)
    return registry


def _contract(name: str, purpose: str, handler: Any, *, required: tuple[str, ...] = (),
              timeout: int = 30_000, side: str = "none", approval: bool = False,
              default: bool = False) -> ToolContract:
    return ToolContract(
        name=name, purpose=purpose, handler=handler, requires_context=required,
        timeout_ms=timeout, side_effect_level=side, requires_human_approval=approval,
        exposed_by_default=default,
    )


def _equipment(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return build_machine_bounds()


def _search(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task = context.get("task_spec") or {}
    query = str(payload.get("query") or " ".join(
        str(task.get(key) or "") for key in ("material", "process_type", "component_type", "objective")
    )).strip()
    if not query:
        return {"status": "insufficient_data", "missing": ["query_or_task_context"]}
    return query_rag({"query": query, "top_k": int(payload.get("top_k") or 8)})


def _bootstrap(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return bootstrap_service(
        task_spec=context.get("task_spec") or {}, question=payload.get("question"),
        query_intent=str(payload.get("query_intent") or "find_literature_prior"),
        max_sources=int(payload.get("max_sources") or 5),
    )


def _recommend_bo(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return LegacyBOCompatibilityAdapter().recommend(
        context["task_spec"], list_bo_training_samples(), context["equipment_snapshot"],
        payload.get("approved_priors") or [],
    )


def _recommend_rag(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    evidence = _search(payload, context)
    return {"status": "success", "source": "reviewed_rag", "evidence": evidence,
            "note": "Evidence is returned for Agent synthesis; no optimum is asserted."}


def _exploratory(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    bounds = (context.get("equipment_snapshot") or {}).get("machine_bounds") or {}
    variables = payload.get("variables") or list(bounds)
    candidate = {}
    for name in variables:
        value = bounds.get(name)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            candidate[name] = (float(value[0]) + float(value[1])) / 2
    return {"status": "success", "source": "equipment_midpoint_exploration",
            "intended_use": "exploratory_trial_only", "is_optimal": False,
            "candidate": candidate, "machine_bounds": bounds}


def _manage_trial(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    service = TrialApplicationService()
    operation = str(payload.get("operation") or "assess")
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    if operation == "assess":
        return service.assess(task_id, {**payload, "task_spec": context.get("task_spec") or {}})
    if operation == "create_plan":
        return service.create_plan(task_id, {**payload, "task_spec": context.get("task_spec") or {},
                                             "machine_bounds": (context.get("equipment_snapshot") or {}).get("machine_bounds") or {}})
    if operation == "get_plan":
        return service.get_plan(str(payload["trial_plan_id"]))
    if operation in {"start_execution", "evaluate"} and not context.get("human_approved"):
        raise PermissionError(f"human approval required for trial operation: {operation}")
    if operation == "start_execution":
        return service.start_execution(str(payload["trial_plan_id"]), payload)
    if operation == "create_result":
        return service.create_result(str(payload["execution_id"]), payload)
    if operation == "evaluate":
        return service.evaluate(str(payload["result_id"]), payload)
    raise ValueError(f"unsupported trial operation: {operation}")


def _bo_iteration(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    recommendation = _recommend_bo(payload, context)
    return {"status": "success", "iteration": int(payload.get("iteration") or 1),
            "recommendation": recommendation, "requires_execution_observation": True}


def _record_result(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict) or not measurements:
        return {"status": "insufficient_data", "missing": ["measurements"]}
    session_id = str(context["session_id"])
    state = get_session_state(session_id)
    observations = list(state.get("agent_observations_json") or [])
    record = {"task_id": payload.get("task_id") or session_id, "parameters": payload.get("parameters") or {},
              "measurements": measurements, "defects": payload.get("defects") or [],
              "attachments": payload.get("attachments") or []}
    observations.append(record)
    update_session_state(session_id, {"agent_observations_json": observations[-100:]})
    return {"status": "success", "recorded": record, "observation_count": len(observations)}


def _create_candidate(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    source_id = payload.get("source_id")
    if not source_id and isinstance(payload.get("source"), dict):
        source_id = register_external_source(payload["source"])["source_id"]
    if not payload.get("claim") or not source_id:
        missing = []
        if not payload.get("claim"):
            missing.append("claim")
        if not source_id:
            missing.append("source_id_or_source")
        return {"status": "insufficient_data", "missing": missing}
    task = context.get("task_spec") or {}
    candidate = build_knowledge_candidate(
        {"source_id": source_id, "credibility_score": payload.get("source_quality_score", 0.5)},
        {"claim": payload["claim"], "material": payload.get("material") or task.get("material"),
         "process_type": payload.get("process_type") or task.get("process_type"),
         "component_type": payload.get("component_type") or task.get("component_type"),
         "parameter": payload.get("parameter") or {}, "condition": payload.get("condition") or {},
         "usable_for": payload.get("usable_for") or [], "not_usable_for": payload.get("not_usable_for") or [],
         "evidence_type": payload.get("evidence_type") or "process_observation",
         "confidence": payload.get("confidence") or 0.0},
    )
    return {"status": "success", "candidate": candidate, "auto_indexed": False, "review_required": True}


def _generate_report(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    body = {**payload, "task_spec": payload.get("task_spec") or context.get("task_spec") or {},
            "equipment_snapshot": context.get("equipment_snapshot") or {}}
    return TaskReportService().generate(task_id, body, payload.get("run_id"))


def _ingest_files(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not paths:
        return {"status": "insufficient_data", "missing": ["paths"]}
    results = [{"path": str(Path(path)), **ingest_file(path)} for path in paths]
    return {"status": "success", "files": results}


def _review_candidate(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return apply_action(str(payload["review_id"]), ReviewActionRequest.model_validate(payload))
