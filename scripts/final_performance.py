from __future__ import annotations

import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "ultrafast_laser_memory"
REPORTS = ROOT / "reports"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - rank) + ordered[upper] * (rank - lower)


def summary(values: list[float], status: str = "implemented", note: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "sample_count": len(values),
        "samples_ms": [round(value, 3) for value in values],
        "p50_ms": round(statistics.median(values), 3) if values else None,
        "p95_ms": round(percentile(values, 0.95), 3) if values else None,
        "p99_ms": round(percentile(values, 0.99), 3) if values else None,
        "min_ms": round(min(values), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
        "note": note,
    }


def measure(call: Callable[[], Any], count: int, warmups: int = 1) -> tuple[list[float], Any]:
    value = None
    for _ in range(warmups):
        value = call()
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        value = call()
        samples.append((time.perf_counter() - started) * 1000)
    return samples, value


def startup(count: int = 11) -> list[float]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT / "src")
    env["ULTRAFAST_MEMORY_ROOT"] = str(PROJECT)
    values = []
    code = "import time;s=time.perf_counter();import ultrafast_memory.apps.api.main;print((time.perf_counter()-s)*1000)"
    for _ in range(count):
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        values.append(float(result.stdout.strip().splitlines()[-1]))
    return values


def copy_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, Any] = {
        "application_startup": summary(
            startup(), note="Fresh import of split FastAPI app; socket startup excluded."
        )
    }
    with tempfile.TemporaryDirectory(
        prefix="ultrafast-final-performance-", ignore_cleanup_errors=True
    ) as temporary:
        temp_root = Path(temporary) / "agent"
        (temp_root / "configs").mkdir(parents=True)
        shutil.copy2(PROJECT / "configs/default.yaml", temp_root / "configs/default.yaml")
        copy_database(PROJECT / "data/ultrafast_memory.db", temp_root / "data/ultrafast_memory.db")
        os.environ["ULTRAFAST_MEMORY_ROOT"] = str(temp_root)
        os.environ["ULTRAFAST_LLM_PROVIDER"] = "mock"
        os.environ["ULTRAFAST_LLM_MODEL"] = "performance-mock"
        sys.path.insert(0, str(PROJECT / "src"))

        from ultrafast_agent.jobs import BackgroundJobService
        from ultrafast_agent.runtime import WorkflowContext
        from ultrafast_bo import BORecommendationService
        from ultrafast_bo.application.governance import BODatasetSliceService
        from ultrafast_integrations.storage.job_repository import SQLiteJobRepository
        from ultrafast_domain.trial import design_trial_plan
        from ultrafast_memory.chat.router.rule_router import rule_route
        from ultrafast_memory.chat.schemas import ChatRequest
        from ultrafast_memory.chat.service import handle_chat_stream_ndjson
        from ultrafast_memory.db.session import get_connection
        from ultrafast_memory.doctor.service import DoctorService
        from ultrafast_memory.equipment.bounds import build_machine_bounds
        from ultrafast_memory.rag.query_service import clear_rag_query_cache, query_rag
        from sklearn.exceptions import ConvergenceWarning

        warnings.filterwarnings("ignore", category=ConvergenceWarning)

        def _count(table: str) -> int:
            with get_connection() as connection:
                return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

        first_event, first_token, total = [], [], []
        for index in range(12):
            request = ChatRequest(
                message=f"final performance {index}", mode="normal", use_skills=False, stream=True
            )
            started = time.perf_counter()
            event_at = None
            token_at = None
            for event in handle_chat_stream_ndjson(request):
                now = time.perf_counter()
                event_at = event_at or now
                if token_at is None and event.get("type") == "delta":
                    token_at = now
            ended = time.perf_counter()
            first_event.append(((event_at or ended) - started) * 1000)
            first_token.append(((token_at or ended) - started) * 1000)
            total.append((ended - started) * 1000)
        metrics["chat_first_event"] = summary(first_event, note="In-process NDJSON, MockLLM.")
        metrics["chat_first_token"] = summary(first_token, note="First delta, MockLLM.")
        metrics["chat_total_response"] = summary(total, note="Complete NDJSON response, MockLLM.")

        query = {
            "query": "TGV 高深径比玻璃通孔 飞秒激光",
            "top_k": 8,
            "index_name": "literature_default",
        }
        rag_cold = []
        rag_result = None
        for _ in range(9):
            clear_rag_query_cache()
            started = time.perf_counter()
            rag_result = query_rag(query)
            rag_cold.append((time.perf_counter() - started) * 1000)
        clear_rag_query_cache()
        query_rag(query)
        rag_warm, warm_result = measure(lambda: query_rag(query), 12, warmups=0)
        metrics["rag_query"] = summary(
            rag_cold,
            note=f"Cold cache; chunks={_count('literature_chunk')}; hits={len((rag_result or {}).get('hits') or [])}.",
        )
        metrics["rag_query_warm_cache"] = summary(
            rag_warm,
            note=f"Revision-scoped cache; cache_hit={warm_result['retrieval_metadata']['cache_hit']}.",
        )

        router_values, route = measure(
            lambda: rule_route("请基于文献分析 TGV 高深径比玻璃通孔加工", {}), 60, 3
        )
        metrics["router"] = summary(
            router_values, note=f"Rule router + equipment context; skill={route.primary_skill}."
        )
        equipment_values, equipment = measure(build_machine_bounds, 40, 2)
        metrics["equipment_profile_read"] = summary(
            equipment_values, note=f"active={equipment.get('active')}"
        )

        def db_query() -> int:
            with get_connection() as connection:
                return connection.execute("SELECT COUNT(*) FROM literature_chunk").fetchone()[0]

        db_values, rows = measure(db_query, 100, 5)
        metrics["database_query"] = summary(db_values, note=f"rows={rows}")

        workflow_context = WorkflowContext.create("performance-session", "performance-task")

        def transition_workflow() -> Any:
            nonlocal workflow_context
            workflow_context, event = workflow_context.transition(
                "stage_changed", "performance event", stage="benchmark"
            )
            return event

        workflow_values, workflow_event = measure(transition_workflow, 100, 3)
        metrics["workflow_event_processing"] = summary(
            workflow_values, note=f"Immutable transition; final_sequence={workflow_event.sequence}."
        )

        bounds = {
            "laser_power_W": [1.0, 20.0],
            "frequency_kHz": [50.0, 500.0],
            "scan_speed_mm_s": [10.0, 1000.0],
            "passes": [1, 20],
        }
        samples = [
            {
                "sample_id": f"perf-{index}",
                "valid_for_training": True,
                "x_parameters": {
                    "laser_power_W": 1 + 19 * index / 39,
                    "frequency_kHz": 50 + 450 * index / 39,
                    "scan_speed_mm_s": 10 + 990 * index / 39,
                    "passes": 1 + index % 20,
                },
                "y_metrics": {"quality_score": 0.2 * index + 1},
                "material": "performance_material",
                "process_type": "milling",
                "equipment_profile_id": "performance_equipment",
                "target_metric": "quality_score",
            }
            for index in range(40)
        ]
        machine = {
            "active": True, "revision_id": "performance",
            "equipment_profile_id": "performance_equipment", "machine_bounds": bounds,
        }
        slice_values, slice_result = measure(
            lambda: BODatasetSliceService().select(
                samples, material="performance_material", process_type="milling",
                equipment_profile_id="performance_equipment", target_metric="quality_score",
                feature_schema_version="1.0",
            ),
            100, 3,
        )
        metrics["bo_dataset_slice"] = summary(
            slice_values, note=f"Strict material/process/equipment/target slice; selected={len(slice_result[0])}."
        )
        bo_values, bo_result = measure(
            lambda: BORecommendationService().recommend(
                {
                    "material": "performance_material", "process_type": "milling",
                    "objective_metric": "quality_score", "random_seed": 42,
                    "optimizer_restarts": 0,
                },
                samples, machine,
            ),
            7,
            1,
        )
        metrics["bo_recommendation"] = summary(
            bo_values,
            note=f"Real GPR application service; status={bo_result['model_status']}; bo_invoked={bo_result['bo_invoked']}.",
        )

        job_repository = SQLiteJobRepository()
        job_service = BackgroundJobService(job_repository)
        job_counter = 0

        def enqueue_and_claim() -> Any:
            nonlocal job_counter
            job_counter += 1
            job, _ = job_service.create("performance_noop", {"index": job_counter})
            claimed = job_repository.claim_next()
            if claimed is None or claimed.job_id != job.job_id:
                raise RuntimeError("job claim benchmark lost queue ordering")
            job_repository.update(claimed.job_id, status="succeeded", output={}, finished_at=datetime.now(timezone.utc).isoformat())
            return claimed

        job_values, claimed_job = measure(enqueue_and_claim, 30, 2)
        metrics["job_enqueue_and_claim"] = summary(
            job_values, note=f"SQLite transaction path; last_job={claimed_job.job_id}."
        )
        metrics["ocr_per_page"] = summary(
            [], status="not_measured",
            note="No authorized scanned-PDF benchmark corpus or installed PaddleOCR model was supplied; structural OCR job tests are reported separately.",
        )
        trial_values, trial_result = measure(
            lambda: design_trial_plan(
                "performance-task",
                {"process_type": "TGV_drilling", "targets": {"depth_min_um": 450}},
                "simple_trial_cut",
                bounds,
                "tgv",
            ),
            100,
            3,
        )
        metrics["trial_plan_generation"] = summary(
            trial_values,
            note=f"Implemented domain policy; matrix_rows={len(trial_result.parameter_matrix)}.",
        )

        def one_chat(index: int) -> float:
            started = time.perf_counter()
            list(
                handle_chat_stream_ndjson(
                    ChatRequest(
                        message=f"concurrent session {index}",
                        mode="normal",
                        use_skills=False,
                        stream=True,
                    )
                )
            )
            return (time.perf_counter() - started) * 1000

        concurrent = []
        for batch in range(3):
            with ThreadPoolExecutor(max_workers=5) as executor:
                concurrent.extend(executor.map(one_chat, range(batch * 5, batch * 5 + 5)))
        metrics["concurrent_5_sessions"] = summary(
            concurrent, note="Three batches of five concurrent MockLLM chat sessions."
        )

        before = (temp_root / "data/ultrafast_memory.db").stat().st_size
        for index in range(20):
            one_chat(100 + index)
        after = (temp_root / "data/ultrafast_memory.db").stat().st_size
        metrics["database_growth_20_chats"] = {
            "status": "implemented",
            "sample_count": 1,
            "samples_ms": [],
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "min_ms": None,
            "max_ms": None,
            "bytes_before": before,
            "bytes_after": after,
            "growth_bytes": after - before,
            "note": "Temporary database growth after 20 persisted chat sessions.",
        }
        doctor_values, doctor_result = measure(lambda: DoctorService().run(), 3, 0)
        metrics["doctor"] = summary(
            doctor_values, note=f"status={doctor_result['status']}; external_call=False."
        )

    baseline_path = REPORTS / "baseline_performance.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    comparisons = {}
    for name, metric in metrics.items():
        old = (baseline.get("metrics") or {}).get(name) or {}
        if metric.get("p50_ms") is not None and old.get("p50_ms") not in {None, 0}:
            comparisons[name] = {
                "baseline_p50_ms": old["p50_ms"],
                "final_p50_ms": metric["p50_ms"],
                "p50_change_percent": round((metric["p50_ms"] / old["p50_ms"] - 1) * 100, 2),
                "baseline_p95_ms": old.get("p95_ms"),
                "final_p95_ms": metric.get("p95_ms"),
                "p95_change_percent": round(
                    (metric["p95_ms"] / old["p95_ms"] - 1) * 100, 2
                )
                if metric.get("p95_ms") is not None and old.get("p95_ms") not in {None, 0}
                else None,
                "comparable": name != "chat_first_event",
                "comparison_note": (
                    "Final stream emits its first event only after the shared sync workflow completes; "
                    "the baseline emitted metadata before workflow execution, so percentage regression is not like-for-like."
                    if name == "chat_first_event" else None
                ),
            }
    comparable = [item for item in comparisons.values() if item["comparable"]]
    acceptance_checks = {
        "first_event_p95_under_500_ms": metrics["chat_first_event"]["p95_ms"] < 500,
        "route_p95_under_800_ms": metrics["router"]["p95_ms"] < 800,
        "equipment_p95_under_300_ms": metrics["equipment_profile_read"]["p95_ms"] < 300,
        "rag_p95_under_2500_ms": metrics["rag_query"]["p95_ms"] < 2500,
        "bo_p95_under_3000_ms": metrics["bo_recommendation"]["p95_ms"] < 3000,
        "first_token_p95_under_2500_ms": metrics["chat_first_token"]["p95_ms"] < 2500,
        "chat_total_p95_under_12000_ms": metrics["chat_total_response"]["p95_ms"] < 12000,
        "five_session_p95_under_12000_ms": metrics["concurrent_5_sessions"]["p95_ms"] < 12000,
        "revision_cache_is_faster": metrics["rag_query_warm_cache"]["p50_ms"] < metrics["rag_query"]["p50_ms"],
        "database_growth_20_chats_under_1_mib": metrics["database_growth_20_chats"]["growth_bytes"] < 1024 * 1024,
        "baseline_p50_regression_within_10_percent": all(
            item["p50_change_percent"] <= 10 for item in comparable
        ),
        "baseline_p95_regression_within_10_percent": all(
            item["p95_change_percent"] is None or item["p95_change_percent"] <= 10
            for item in comparable
        ),
    }
    acceptance = {
        "status": "pass" if all(acceptance_checks.values()) else "fail",
        "checks": acceptance_checks,
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_head_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True
        ).stdout.strip(),
        "worktree_included_uncommitted_refactor": True,
        "external_llm_calls": False,
        "live_database_mutated": False,
        "metrics": metrics,
        "baseline_comparison": comparisons,
        "acceptance": acceptance,
    }
    (REPORTS / "final_performance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows_text = [
        f"| {name} | {metric['status']} | {metric.get('p50_ms', 'N/A')} | {metric.get('p95_ms', 'N/A')} | {metric.get('p99_ms', 'N/A')} | {metric['note']} |"
        for name, metric in metrics.items()
    ]
    (REPORTS / "final_performance.md").write_text(
        "\n".join(
            [
                "# Final performance",
                "",
                "All measurements use MockLLM and a temporary online backup of the live SQLite database.",
                "",
                "| Metric | Status | P50 ms | P95 ms | P99 ms | Scope |",
                "|---|---|---:|---:|---:|---|",
                *rows_text,
                "",
                f"Acceptance: **{acceptance['status']}** ({sum(acceptance_checks.values())}/{len(acceptance_checks)} checks).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({name: {"p50_ms": value.get("p50_ms"), "p95_ms": value.get("p95_ms")} for name, value in metrics.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
