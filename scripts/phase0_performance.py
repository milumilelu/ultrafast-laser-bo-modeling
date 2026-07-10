from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "ultrafast_laser_memory"
REPORTS_DIR = REPO_ROOT / "reports"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(values: list[float], status: str = "implemented", note: str = "") -> dict[str, Any]:
    rounded = [round(value, 3) for value in values]
    return {
        "status": status,
        "sample_count": len(values),
        "samples_ms": rounded,
        "min_ms": round(min(values), 3) if values else None,
        "p50_ms": round(statistics.median(values), 3) if values else None,
        "p95_ms": round(percentile(values, 0.95), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
        "note": note,
    }


def measure(call: Callable[[], Any], samples: int, warmups: int = 1) -> tuple[list[float], Any]:
    result: Any = None
    for _ in range(warmups):
        result = call()
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        result = call()
        values.append((time.perf_counter() - start) * 1000)
    return values, result


def startup_samples(samples: int = 5) -> list[float]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(AGENT_ROOT / "src")
    env["ULTRAFAST_MEMORY_ROOT"] = str(AGENT_ROOT)
    env["ULTRAFAST_LLM_PROVIDER"] = "mock"
    env["ULTRAFAST_LLM_MODEL"] = "baseline-mock"
    code = (
        "import time; s=time.perf_counter(); "
        "import ultrafast_memory.app.api; "
        "print((time.perf_counter()-s)*1000)"
    )
    values = []
    for _ in range(samples):
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=AGENT_ROOT,
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
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, Any] = {}
    metrics["application_startup"] = summarize(
        startup_samples(), note="Fresh Python process importing ultrafast_memory.app.api; server socket startup excluded."
    )

    with tempfile.TemporaryDirectory(
        prefix="ultrafast-phase0-perf-", ignore_cleanup_errors=True
    ) as tmp:
        temp_root = Path(tmp) / "agent"
        (temp_root / "configs").mkdir(parents=True)
        shutil.copy2(AGENT_ROOT / "configs/default.yaml", temp_root / "configs/default.yaml")
        copy_database(AGENT_ROOT / "data/ultrafast_memory.db", temp_root / "data/ultrafast_memory.db")

        os.environ["ULTRAFAST_MEMORY_ROOT"] = str(temp_root)
        os.environ["ULTRAFAST_LLM_PROVIDER"] = "mock"
        os.environ["ULTRAFAST_LLM_MODEL"] = "baseline-mock"
        sys.path.insert(0, str(AGENT_ROOT / "src"))
        sys.path.insert(0, str(REPO_ROOT))

        from ultrafast_memory.bo.bo_engine_adapter import call_bo_recommendation
        from ultrafast_memory.chat.router.rule_router import rule_route
        from ultrafast_memory.chat.schemas import ChatRequest
        from ultrafast_memory.chat.service import handle_chat_stream_ndjson
        from ultrafast_memory.db.session import get_connection
        from ultrafast_memory.equipment.bounds import build_machine_bounds
        from ultrafast_memory.rag.query_service import query_rag

        first_event = []
        first_token = []
        totals = []
        for index in range(10):
            request = ChatRequest(
                message=f"Phase 0 latency baseline {index}",
                mode="normal",
                use_skills=False,
                stream=True,
            )
            started = time.perf_counter()
            event_time = None
            token_time = None
            for event in handle_chat_stream_ndjson(request):
                now = time.perf_counter()
                if event_time is None:
                    event_time = now
                if token_time is None and event.get("type") == "delta":
                    token_time = now
            finished = time.perf_counter()
            first_event.append(((event_time or finished) - started) * 1000)
            first_token.append(((token_time or finished) - started) * 1000)
            totals.append((finished - started) * 1000)
        metrics["chat_first_event"] = summarize(
            first_event,
            note="In-process /chat/stream_ndjson generator with MockLLM; HTTP transport excluded.",
        )
        metrics["chat_first_token"] = summarize(
            first_token,
            note="First NDJSON delta event with MockLLM; HTTP transport excluded.",
        )
        metrics["chat_total_response"] = summarize(
            totals,
            note="Completion of NDJSON stream with MockLLM; HTTP transport excluded.",
        )

        rag_values, rag_result = measure(
            lambda: query_rag(
                {
                    "query": "TGV 高深径比玻璃通孔 飞秒激光",
                    "filters": {},
                    "top_k": 8,
                    "index_name": "literature_default",
                    "purpose": "literature_background",
                }
            ),
            samples=7,
            warmups=1,
        )
        metrics["rag_query"] = summarize(
            rag_values,
            status="implemented",
            note=f"Temporary copy of production-size SQLite index; hits={len(rag_result.get('hits') or [])}; evidence_status={rag_result.get('evidence_status')}",
        )

        router_values, router_result = measure(
            lambda: rule_route("请基于文献分析 TGV 高深径比玻璃通孔加工", {}),
            samples=50,
            warmups=3,
        )
        metrics["router"] = summarize(
            router_values,
            note=f"Rule router including equipment-context read; primary_skill={getattr(router_result, 'primary_skill', None)}",
        )
        equipment_values, equipment_result = measure(build_machine_bounds, samples=30, warmups=2)
        metrics["equipment_profile_read"] = summarize(
            equipment_values,
            note=f"Active equipment profile and machine-bound construction; active={equipment_result.get('active')}",
        )

        def db_query() -> int:
            with get_connection() as connection:
                return int(connection.execute("SELECT COUNT(*) FROM literature_chunk").fetchone()[0])

        db_values, db_result = measure(db_query, samples=100, warmups=5)
        metrics["database_query"] = summarize(
            db_values, note=f"SQLite open/read/close COUNT query; rows={db_result}"
        )

        adapter_values, adapter_result = measure(
            lambda: call_bo_recommendation({"material": "SiC"}, "data/exports/bo_training_samples.csv"),
            samples=100,
            warmups=2,
        )
        metrics["bo_agent_adapter"] = summarize(
            adapter_values,
            status="stub",
            note=f"Not a real recommendation; adapter returns model_status={adapter_result.get('model_status')}.",
        )

        from src.interactive_bo import init_task, recommend_parameters

        legacy_output = Path(tmp) / "legacy_bo_outputs"
        legacy_config = {
            "_root": str(REPO_ROOT),
            "data_path": str(REPO_ROOT / "data/processed/updated_experiments.csv"),
            "output_dir": str(legacy_output),
            "random_seed": 42,
            "bo_candidate_grid_size": 500,
            "lambda_sa": 0.25,
        }
        legacy_state = init_task(
            legacy_config,
            "SiC",
            "balanced",
            process_type="milling",
            target_depth_um=20,
            Sa_max_um=2.0,
        )

        def legacy_bo() -> dict[str, Any]:
            state = copy.deepcopy(legacy_state)
            state["history"] = []
            return recommend_parameters(state, "balanced")

        legacy_values, legacy_result = measure(legacy_bo, samples=5, warmups=1)
        metrics["bo_recommendation"] = summarize(
            legacy_values,
            note=f"Real legacy-root recommendation path; model_status={legacy_result.get('model_status')}; candidate_grid_size=500.",
        )

    metrics["trial_plan_generation"] = summarize(
        [], status="not_found", note="No trial planning module/API/service exists at the Phase 0 baseline."
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        ).stdout.strip(),
        "platform": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "measurement_clock": "time.perf_counter",
            "external_llm_calls": False,
            "database_copy_used": True,
        },
        "metrics": metrics,
    }
    (REPORTS_DIR / "baseline_performance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = []
    for name, metric in metrics.items():
        rows.append(
            f"| {name} | {metric['status']} | {metric['sample_count']} | {metric['p50_ms'] if metric['p50_ms'] is not None else 'N/A'} | {metric['p95_ms'] if metric['p95_ms'] is not None else 'N/A'} | {metric['note']} |"
        )
    markdown = "\n".join(
        [
            "# Phase 0 performance baseline",
            "",
            f"- HEAD: `{payload['head_commit']}`",
            "- External LLM/network calls: disabled",
            "- RAG/equipment/database measurements: temporary SQLite backup, not the live database",
            "- Units: milliseconds",
            "",
            "| Metric | Status | Samples | P50 | P95 | Scope |",
            "|---|---:|---:|---:|---:|---|",
            *rows,
            "",
            "The `bo_agent_adapter` timing is diagnostic only because the adapter is a stub. The authoritative baseline for a real BO recommendation is `bo_recommendation`, measured through the legacy root project. Trial-plan timing is unavailable because that capability does not exist at this baseline.",
            "",
        ]
    )
    (REPORTS_DIR / "baseline_performance.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({name: {"status": value["status"], "p50_ms": value["p50_ms"], "p95_ms": value["p95_ms"]} for name, value in metrics.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
