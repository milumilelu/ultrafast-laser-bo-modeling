from __future__ import annotations

from pathlib import Path
from typing import Any

from ultrafast_agent.runtime import ToolContract, ToolRegistry
from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_integrations.storage.read_models import list_bo_training_samples
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.ingestion.pipeline import ingest_file
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge as bootstrap_service
from ultrafast_memory.process_workflow.closure import bo_sample_eligibility, quality_decision
from ultrafast_memory.process_workflow.repository import ProcessWorkflowRepository
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.reports.task_report_service import TaskReportService
from ultrafast_memory.trial.service import TrialApplicationService


FOREGROUND_SAFE_TOOL_NAMES = {
    "get_equipment_context",
    "search_knowledge",
    "recommend_parameters_bo",
    "recommend_parameters_rag",
    "propose_exploratory_parameters",
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
        _contract("get_equipment_context", "Read authoritative equipment revision and physical bounds.", _equipment, default=True, cache="equipment_revision"),
        _contract("search_knowledge", "Search reviewed internal knowledge with traceable evidence.", _search, cache="turn"),
        _contract("recommend_parameters_bo", "Compute a bounded BO recommendation from validated matching samples.", _recommend_bo, timeout=60_000, required=("equipment_snapshot.machine_bounds",)),
        _contract("recommend_parameters_rag", "Retrieve reviewed evidence for a conservative parameter candidate.", _recommend_rag),
        _contract("propose_exploratory_parameters", "Create an explicitly exploratory trial-only candidate inside equipment bounds.", _exploratory),
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
              cache: str = "none", required: tuple[str, ...] = ()) -> ToolContract:
    return ToolContract(
        name=name, purpose=purpose, handler=handler, timeout_ms=timeout,
        side_effect_level=side, requires_human_approval=approval,
        exposed_by_default=default, cache_policy=cache, requires_context=required,
    )


def _task(context: dict[str, Any]) -> dict[str, Any]:
    working = context.get("working_context") or {}
    return dict(working.get("task") or context.get("task_spec") or {})


def _legacy_task(context: dict[str, Any]) -> dict[str, Any]:
    task = _task(context)
    material = task.get("material")
    geometry = task.get("geometry") or {}
    return {
        **task,
        "material": material.get("name") if isinstance(material, dict) else material,
        "process_type": task.get("process_type") or task.get("process_intent"),
        "objective": task.get("objective") or task.get("targets") or "process_quality",
        "thickness_mm": task.get("thickness_mm") or geometry.get("workpiece_thickness_mm"),
    }


def _equipment(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "summary": "已读取当前设备版本与物理边界。", **build_machine_bounds()}


def _search(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task = _legacy_task(context)
    query = str(payload.get("query") or " ".join(
        str(task.get(key) or "") for key in ("material", "process_type", "objective")
    )).strip()
    if not query:
        return {"status": "insufficient_data", "summary": "缺少可检索的任务描述。", "missing": ["query_or_task_context"]}
    result = query_rag({"query": query, "top_k": int(payload.get("top_k") or 8)})
    return {"status": "success", "summary": "内部知识检索完成。", "query": query, "result": result,
            "hits": result.get("hits") or [],
            "provenance": [{"source_type": "reviewed_rag"}]}


def _bootstrap(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return bootstrap_service(task_spec=_legacy_task(context), question=payload.get("question"),
                             query_intent=str(payload.get("query_intent") or "find_literature_prior"),
                             max_sources=int(payload.get("max_sources") or 5))


def _parameter_result(*, status: str, parameters: dict[str, Any], source_type: str,
                      source_refs: list[Any] | None = None, data_support: dict[str, Any] | None = None,
                      uncertainty: dict[str, Any] | None = None, limitations: list[str] | None = None,
                      evidence_level: str = "unknown") -> dict[str, Any]:
    return {
        "status": status, "parameters": parameters, "source_type": source_type,
        "source_refs": source_refs or [], "data_support": data_support or {},
        "evidence_level": evidence_level, "uncertainty": uncertainty or {},
        "limitations": limitations or [], "recommended_use": ["trial"],
        "provenance": [{"source_type": source_type, "source_refs": source_refs or []}],
    }


def _recommend_bo(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    raw = LegacyBOCompatibilityAdapter().recommend(
        _legacy_task(context), list_bo_training_samples(),
        context.get("equipment_snapshot") or build_machine_bounds(),
        payload.get("approved_priors") or [],
    )
    status = str(raw.get("status") or "success")
    parameters = raw.get("parameters") or raw.get("candidate") or raw.get("recommended_parameters") or {}
    return _parameter_result(
        status="insufficient_data" if status == "insufficient_data" else "success",
        parameters=parameters, source_type="bo",
        source_refs=list(raw.get("source_refs") or raw.get("sample_ids") or []),
        data_support={"raw_status": status, "sample_count": raw.get("sample_count")},
        uncertainty=raw.get("uncertainty") or {}, limitations=list(raw.get("limitations") or []),
        evidence_level="validated_samples",
    ) | {"raw_result": raw}


def _recommend_rag(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    evidence = _search(payload, context)
    if evidence.get("status") == "insufficient_data":
        return _parameter_result(status="insufficient_data", parameters={}, source_type="reviewed_rag",
                                 limitations=["缺少检索上下文"], evidence_level="none")
    return _parameter_result(status="success", parameters=payload.get("parameters") or {},
                             source_type="reviewed_rag", data_support={"evidence": evidence},
                             limitations=["检索证据需由主 Agent 结合任务解释，不代表全局最优。"],
                             evidence_level="reviewed_evidence")


def _exploratory(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    bounds = (context.get("equipment_snapshot") or build_machine_bounds()).get("machine_bounds") or {}
    variables = payload.get("variables") or list(bounds)
    candidate: dict[str, Any] = {}
    for name in variables:
        value = bounds.get(name)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            candidate[name] = (float(value[0]) + float(value[1])) / 2
    return _parameter_result(status="exploratory", parameters=candidate, source_type="llm_exploration",
                             data_support={"machine_bounds": bounds}, evidence_level="hypothesis",
                             limitations=["仅用于试切冷启动；未经验证，不得直接晋升为正式参数。"])


def _manage_trial(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    service = TrialApplicationService()
    operation = str(payload.get("operation") or "get")
    task_id = str(payload.get("task_id") or context.get("session_id") or "task")
    if operation == "create":
        result = service.create_plan(task_id, {
            **payload, "trial_mode": payload.get("trial_mode") or "simple_trial_cut",
            "task_spec": _legacy_task(context),
            "machine_bounds": (context.get("equipment_snapshot") or build_machine_bounds()).get("machine_bounds") or {},
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
