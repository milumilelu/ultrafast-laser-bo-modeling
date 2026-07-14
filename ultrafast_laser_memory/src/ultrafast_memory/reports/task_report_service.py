from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ultrafast_agent.runtime.events import redact_public_data
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.core.config import resolve_path
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_shared.db.unit_of_work import UnitOfWork


class TaskReportService:
    def __init__(self, events: RuntimeEventRepository | None = None):
        self.events = events or RuntimeEventRepository()

    def generate(self, task_id: str, payload: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
        init_database()
        safe_task_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id).strip("._") or "task"
        output_dir = resolve_path(f"data/reports/tasks/{safe_task_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        trace = self.events.list_run_events(run_id) if run_id else list(payload.get("execution_trace") or [])
        report = redact_public_data(self._report_payload(task_id, payload, trace))
        json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        markdown_text = self._markdown(report)
        json_path = output_dir / "task_report.json"
        markdown_path = output_dir / "task_report.md"
        json_path.write_text(json_text, encoding="utf-8")
        markdown_path.write_text(markdown_text, encoding="utf-8")
        content_hash = hashlib.sha256((json_text + markdown_text).encode("utf-8")).hexdigest()
        report_id = f"task-report-{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO task_report VALUES (?,?,?,?,?,?,?,?)",
                (
                    report_id,
                    task_id,
                    run_id,
                    str(markdown_path),
                    str(json_path),
                    content_hash,
                    "completed",
                    created_at,
                ),
            )
            uow.commit()
        return {
            "report_id": report_id,
            "task_id": task_id,
            "run_id": run_id,
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
            "content_hash": content_hash,
            "status": "completed",
            "created_at": created_at,
            "report": report,
        }

    def get_latest(self, task_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_report WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"task report not found: {task_id}")
        result = dict(row)
        path = Path(result["json_path"])
        result["report"] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return result

    def _report_payload(
        self, task_id: str, payload: dict[str, Any], trace: list[dict[str, Any]]
    ) -> dict[str, Any]:
        task = payload.get("task_spec") or {}
        equipment = payload.get("equipment") or payload.get("equipment_snapshot") or {}
        evidence = payload.get("evidence") or payload.get("evidence_pack") or {}
        trial = payload.get("trial") or payload.get("trial_plan") or {}
        knowledge = payload.get("knowledge_gate") or payload.get("knowledge_gate_decision") or {}
        bo = payload.get("bo") or payload.get("bo_recommendation") or payload.get("bo_status") or {}
        quality = payload.get("quality_plan") or {}
        machine_bounds = equipment.get("machine_bounds") or {}
        recommended_parameters = bo.get("recommended_parameters") or {}
        equipment_clipping = {
            name: {
                "recommended": value,
                "machine_bounds": machine_bounds.get(name),
                "within_bounds": _within(value, machine_bounds.get(name)),
            }
            for name, value in recommended_parameters.items()
        }
        timings = [
            {
                "sequence": item.get("sequence"),
                "stage": item.get("stage"),
                "tool": item.get("tool"),
                "duration_ms": item.get("duration_ms"),
                "cache_hit": item.get("cache_hit"),
            }
            for item in trace
            if item.get("duration_ms") is not None
        ]
        return {
            "task_id": task_id,
            "business_state": payload.get("business_state"),
            "substatus": payload.get("substatus"),
            "task_objective": task.get("objective") or task.get("targets") or payload.get("task_objective"),
            "material_and_component": {
                "material": task.get("material"),
                "material_grade": task.get("material_grade"),
                "component_type": task.get("component_type"),
                "process_type": task.get("process_type"),
            },
            "equipment": {
                "profile_id": equipment.get("equipment_profile_id") or equipment.get("profile_id"),
                "profile_name": equipment.get("profile_name"),
                "revision_id": equipment.get("revision_id"),
                "machine_bounds": machine_bounds,
            },
            "literature_and_citations": evidence.get("citations") or payload.get("citations") or [],
            "evidence_status": evidence.get("evidence_status") or payload.get("evidence_status"),
            "process_route": payload.get("process_route") or {},
            "trial": {
                "mode": trial.get("trial_mode"),
                "representative_geometry": trial.get("representative_geometry"),
                "parameter_matrix": trial.get("parameter_matrix"),
                "acceptance_criteria": trial.get("acceptance_criteria"),
                "stop_conditions": trial.get("stop_conditions"),
                "result": payload.get("trial_result"),
            },
            "knowledge_review": knowledge,
            "parameter_window_and_source": {
                "trial_parameter_matrix": trial.get("parameter_matrix") or [],
                "recommended_parameters": recommended_parameters,
                "source": "approved_knowledge_and_equipment_bounds"
                if bo.get("knowledge_approval_ids")
                else "validated_experiments_or_equipment_bounds",
                "knowledge_approval_ids": bo.get("knowledge_approval_ids") or [],
                "machine_bounds_revision": bo.get("machine_bounds_revision")
                or equipment.get("revision_id"),
            },
            "equipment_clipping": equipment_clipping,
            "bo": {
                "model_status": bo.get("model_status"),
                "valid_sample_count": bo.get("sample_count") or bo.get("valid_sample_count"),
                "recommended_parameters": recommended_parameters,
                "uncertainty": (bo.get("prediction") or {}).get("uncertainty"),
                "approval_ids": bo.get("knowledge_approval_ids") or [],
            },
            "quality_plan": quality,
            "risks": payload.get("risks") or [],
            "next_step": payload.get("next_step") or (payload.get("execution_plan") or {}).get("status"),
            "execution_timings": timings,
            "execution_trace_count": len(trace),
        }

    def _markdown(self, report: dict[str, Any]) -> str:
        material = report["material_and_component"]
        equipment = report["equipment"]
        trial = report["trial"]
        bo = report["bo"]
        return "\n".join(
            [
                f"# Task report: {report['task_id']}",
                "",
                "## Task",
                "",
                f"- Objective: `{_compact(report['task_objective'])}`",
                f"- Material: `{material.get('material')}` / `{material.get('material_grade')}`",
                f"- Component/process: `{material.get('component_type')}` / `{material.get('process_type')}`",
                "",
                "## Equipment and evidence",
                "",
                f"- Equipment: `{equipment.get('profile_name')}`; revision `{equipment.get('revision_id')}`",
                f"- Evidence status: `{report.get('evidence_status')}`",
                f"- Citations: {len(report.get('literature_and_citations') or [])}",
                "",
                "## Process and trial",
                "",
                f"- Route: `{_compact(report.get('process_route'))}`",
                f"- Trial mode: `{trial.get('mode')}`",
                f"- Representative geometry: `{_compact(trial.get('representative_geometry'))}`",
                f"- Parameter window/source: `{_compact(report.get('parameter_window_and_source'))}`",
                f"- Equipment clipping: `{_compact(report.get('equipment_clipping'))}`",
                f"- Stop conditions: `{_compact(trial.get('stop_conditions'))}`",
                "",
                "## Review and BO",
                "",
                f"- Knowledge gate: `{_compact(report.get('knowledge_review'))}`",
                f"- BO model status: `{bo.get('model_status')}`",
                f"- Valid samples: `{bo.get('valid_sample_count')}`",
                f"- Recommendation: `{_compact(bo.get('recommended_parameters'))}`",
                "",
                "## Quality, risks, and next step",
                "",
                f"- Quality plan: `{_compact(report.get('quality_plan'))}`",
                f"- Risks: `{_compact(report.get('risks'))}`",
                f"- Next step: `{report.get('next_step')}`",
                f"- Timed trace events: `{len(report.get('execution_timings') or [])}`",
                "",
            ]
        )


def _compact(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 500 else text[:497] + "..."


def _within(value: Any, bounds: Any) -> bool | None:
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        return None
    try:
        return float(bounds[0]) <= float(value) <= float(bounds[1])
    except (TypeError, ValueError):
        return None
