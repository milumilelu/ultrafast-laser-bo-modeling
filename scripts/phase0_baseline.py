from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "ultrafast_laser_memory"
REPORTS_DIR = REPO_ROOT / "reports"
HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=REPO_ROOT,
    text=True,
    encoding="utf-8",
    capture_output=True,
    check=True,
).stdout.strip()


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "command": subprocess.list2cmdline(command),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.rstrip(),
        "stderr": completed.stderr.rstrip(),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite_summary(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        row_counts = {}
        for table in tables:
            quoted = table.replace('"', '""')
            row_counts[table] = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted}"'
            ).fetchone()[0]
        return {"integrity_check": integrity, "table_row_counts": row_counts}


def backup_baseline() -> dict[str, Any]:
    backup_root = AGENT_ROOT / "data/backups/pre-agent-refactor" / HEAD[:12]
    database_dir = backup_root / "database"
    config_dir = backup_root / "configs"
    database_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    source_db = AGENT_ROOT / "data/ultrafast_memory.db"
    target_db = database_dir / source_db.name
    with sqlite3.connect(source_db) as source, sqlite3.connect(target_db) as target:
        source.backup(target)
    source_summary = _sqlite_summary(source_db)
    backup_summary = _sqlite_summary(target_db)

    copied_configs = []
    for source in [AGENT_ROOT / "configs/default.yaml", AGENT_ROOT / "configs/llm.local.json"]:
        if source.exists():
            target = config_dir / source.name
            shutil.copy2(source, target)
            copied_configs.append(
                {
                    "source": str(source.relative_to(REPO_ROOT).as_posix()),
                    "backup": str(target.relative_to(REPO_ROOT).as_posix()),
                    "bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "head_commit": HEAD,
        "backup_root": str(backup_root.relative_to(REPO_ROOT).as_posix()),
        "database": {
            "source": str(source_db.relative_to(REPO_ROOT).as_posix()),
            "backup": str(target_db.relative_to(REPO_ROOT).as_posix()),
            "bytes": target_db.stat().st_size,
            "source_sha256": _sha256(source_db),
            "backup_sha256": _sha256(target_db),
            "source_sqlite_summary": source_summary,
            "backup_sqlite_summary": backup_summary,
            "logical_snapshot_matches": source_summary == backup_summary,
        },
        "configs": copied_configs,
        "secret_store_copied": False,
        "secret_store_note": "DPAPI/API-key material is intentionally excluded; it remains local and git-ignored.",
    }
    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def run_tests() -> list[dict[str, Any]]:
    return [
        _run([sys.executable, "-m", "pytest", "-q", "tests"], REPO_ROOT),
        _run([sys.executable, "-m", "pytest", "-q"], AGENT_ROOT),
    ]


def capture_cli() -> list[dict[str, Any]]:
    agent_env = os.environ.copy()
    agent_env["PYTHONPATH"] = str(AGENT_ROOT / "src")
    agent_env["ULTRAFAST_MEMORY_ROOT"] = str(AGENT_ROOT)
    agent_env["ULTRAFAST_LLM_PROVIDER"] = "mock"
    agent_env["ULTRAFAST_LLM_MODEL"] = "baseline-mock"
    return [
        _run([sys.executable, "main.py", "--help"], REPO_ROOT),
        _run([sys.executable, "-m", "ultrafast_memory.app.cli", "--help"], AGENT_ROOT, agent_env),
        _run([sys.executable, "-m", "ultrafast_memory.app.cli", "rag", "status"], AGENT_ROOT, agent_env),
        _run([sys.executable, "-m", "ultrafast_memory.app.launcher", "--help"], AGENT_ROOT, agent_env),
    ]


def _sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key.endswith("_id") or key in {"created_at", "updated_at", "started_at", "finished_at"}:
                sanitized[key] = "<dynamic>" if item is not None else None
            else:
                sanitized[key] = _sanitize(item)
        return sanitized
    return value


def capture_api_golden() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="ultrafast-phase0-golden-", ignore_cleanup_errors=True
    ) as tmp:
        root = Path(tmp)
        (root / "configs").mkdir(parents=True)
        shutil.copy2(AGENT_ROOT / "configs/default.yaml", root / "configs/default.yaml")
        old_env = {
            name: os.environ.get(name)
            for name in ("ULTRAFAST_MEMORY_ROOT", "ULTRAFAST_LLM_PROVIDER", "ULTRAFAST_LLM_MODEL")
        }
        os.environ["ULTRAFAST_MEMORY_ROOT"] = str(root)
        os.environ["ULTRAFAST_LLM_PROVIDER"] = "mock"
        os.environ["ULTRAFAST_LLM_MODEL"] = "baseline-mock"
        sys.path.insert(0, str(AGENT_ROOT / "src"))
        try:
            from fastapi.testclient import TestClient
            from ultrafast_memory.app.api import app

            requests = [
                ("GET", "/health", None),
                ("GET", "/equipment/schema", None),
                ("POST", "/llm/test", None),
                (
                    "POST",
                    "/chat",
                    {
                        "message": "Phase 0 golden response",
                        "mode": "normal",
                        "use_skills": False,
                        "stream": False,
                    },
                ),
            ]
            responses = []
            with TestClient(app) as client:
                for method, path, body in requests:
                    response = client.request(method, path, json=body)
                    responses.append(
                        {
                            "method": method,
                            "path": path,
                            "request": body,
                            "status_code": response.status_code,
                            "body": _sanitize(response.json()),
                        }
                    )
            return {
                "head_commit": HEAD,
                "environment": "isolated temporary database; MockLLM; no external call",
                "responses": responses,
            }
        finally:
            sys.path = [item for item in sys.path if item != str(AGENT_ROOT / "src")]
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def replay_fixture() -> dict[str, Any]:
    return {
        "fixture_version": 1,
        "head_commit": HEAD,
        "external_network_allowed": False,
        "scenarios": [
            {
                "name": "tgv_high_aspect_ratio_drilling",
                "kind": "chat",
                "request": {"message": "请基于内部文献分析 TGV 高深径比玻璃通孔加工。", "use_skills": True},
                "baseline_expectation": {"primary_skill": "rag_literature_retrieval", "uses_internal_rag": True},
            },
            {
                "name": "t300_cfrp_texture_or_microhole",
                "kind": "chat",
                "request": {"message": "请基于文献分析 T300 CFRP 表面织构或微孔加工。", "use_skills": True},
                "baseline_expectation": {"primary_skill": "rag_literature_retrieval", "uses_internal_rag": True},
            },
            {
                "name": "diamond_crl",
                "kind": "chat",
                "request": {"message": "请规划金刚石 CRL 的超快激光加工。", "use_skills": True},
                "baseline_expectation": {"primary_skill": "crl_task_planning", "requires_clarification": True},
            },
            {
                "name": "equipment_memory_read",
                "kind": "api",
                "request": {"method": "GET", "path": "/equipment/active/machine-bounds"},
                "baseline_expectation": {"active": True, "source": "SQLite equipment profile"},
            },
            {
                "name": "bo_cold_start",
                "kind": "legacy_bo",
                "request": {"process_type": "cutting", "material": "unknown_with_explicit_bounds", "recommendation_type": "balanced"},
                "baseline_expectation": {"model_status": "rule_based_cold_start", "surrogate_model": None},
            },
            {
                "name": "bo_mixed_mode",
                "kind": "legacy_bo",
                "request": {"process_type": "milling", "sample_count_range": [10, 29], "recommendation_type": "balanced"},
                "baseline_expectation": {"model_status": "hybrid_rule_bo"},
            },
            {
                "name": "rag_query",
                "kind": "api",
                "request": {"method": "POST", "path": "/rag/query", "json": {"query": "TGV 高深径比玻璃通孔", "top_k": 8}},
                "baseline_expectation": {"index_name": "literature_default", "traceable_chunks_only": True},
            },
            {
                "name": "knowledge_candidate_pre_review",
                "kind": "api",
                "request": {"method": "GET", "path": "/knowledge/candidates?status=pending_review"},
                "baseline_expectation": {"status": "pending_review", "must_not_affect_bo": True},
            },
        ],
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    backup = backup_baseline()
    tests = run_tests()
    cli = capture_cli()
    golden = capture_api_golden()
    replay = replay_fixture()

    lines = [
        f"Phase 0 baseline test run at {datetime.now(timezone.utc).isoformat()}",
        f"HEAD: {HEAD}",
        "",
    ]
    for result in tests:
        lines.extend(
            [
                f"$ {result['command']}",
                f"cwd: {result['cwd']}",
                f"exit_code: {result['exit_code']}",
                result["stdout"],
                result["stderr"],
                "",
            ]
        )
    (REPORTS_DIR / "baseline_tests.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (REPORTS_DIR / "baseline_cli_outputs.txt").write_text(
        "\n\n".join(
            f"$ {item['command']}\ncwd: {item['cwd']}\nexit_code: {item['exit_code']}\n{item['stdout']}\n{item['stderr']}"
            for item in cli
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    (REPORTS_DIR / "baseline_api_golden_response.json").write_text(
        json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS_DIR / "baseline_chat_replay_fixture.json").write_text(
        json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "head_commit": HEAD,
        "backup": backup,
        "test_exit_codes": [item["exit_code"] for item in tests],
        "cli_exit_codes": [item["exit_code"] for item in cli],
        "golden_status_codes": [item["status_code"] for item in golden["responses"]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(item["exit_code"] == 0 for item in tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
