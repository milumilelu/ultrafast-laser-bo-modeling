from __future__ import annotations

import ast
import csv
import json
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "ultrafast_laser_memory"
REPORTS_DIR = REPO_ROOT / "reports"
EXCLUDED_DIRS = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", ".mypy_cache"}


def _git(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _iter_files(root: Path, pattern: str = "*"):
    if not root.exists():
        return
    for path in root.rglob(pattern):
        if path.is_file() and not any(part in EXCLUDED_DIRS for part in path.parts):
            yield path


def _safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _status_for_source(path: Path, content: str) -> str:
    if re.search(r"\braise\s+NotImplementedError\s*\(", content) or path.name == "index_stub.py":
        return "stub"
    if re.search(r"(?im)^\s*#.*\bTODO\b", content):
        return "partial"
    return "implemented"


def _parse_python(path: Path) -> ast.AST | None:
    try:
        return ast.parse(_safe_text(path), filename=str(path))
    except SyntaxError:
        return None


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        left = _decorator_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _literal_arg(decorator: ast.AST, position: int = 0) -> str | None:
    if not isinstance(decorator, ast.Call) or len(decorator.args) <= position:
        return None
    value = decorator.args[position]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def collect_code_inventory() -> dict[str, Any]:
    python_files = sorted(_iter_files(REPO_ROOT, "*.py"), key=_relative)
    python_records: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []
    api_endpoints: list[dict[str, Any]] = []
    cli_commands: list[dict[str, Any]] = []
    db_model_classes: list[dict[str, Any]] = []
    test_function_count = 0

    for path in python_files:
        content = _safe_text(path)
        status = _status_for_source(path, content)
        record = {"path": _relative(path), "status": status, "bytes": path.stat().st_size}
        python_records.append(record)
        tree = _parse_python(path)
        if tree is None:
            record["parse_error"] = "SyntaxError"
            continue
        if any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and "__name__" in ast.dump(node.test)
            and "__main__" in ast.dump(node.test)
            for node in ast.walk(tree)
        ):
            entrypoints.append({"type": "python_main", "path": _relative(path), "status": status})
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if path.name.startswith("test_") and node.name.startswith("test_"):
                    test_function_count += 1
                for decorator in node.decorator_list:
                    name = _decorator_name(decorator)
                    method = name.rsplit(".", 1)[-1].upper()
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                        api_endpoints.append(
                            {
                                "method": method,
                                "path": _literal_arg(decorator),
                                "function": node.name,
                                "source": _relative(path),
                                "status": status,
                            }
                        )
                    if name.endswith(".command"):
                        cli_commands.append(
                            {
                                "group": name.rsplit(".", 1)[0],
                                "command": _literal_arg(decorator) or node.name.replace("_", "-"),
                                "function": node.name,
                                "source": _relative(path),
                                "status": status,
                            }
                        )
            if isinstance(node, ast.ClassDef):
                bases = {_decorator_name(base) for base in node.bases}
                if "Base" in bases:
                    db_model_classes.append(
                        {"name": node.name, "source": _relative(path), "status": status}
                    )

    pyproject = AGENT_ROOT / "pyproject.toml"
    if pyproject.exists():
        match = re.search(r'ultrafast\s*=\s*"([^"]+)"', _safe_text(pyproject))
        if match:
            entrypoints.append(
                {
                    "type": "project_script",
                    "name": "ultrafast",
                    "target": match.group(1),
                    "source": _relative(pyproject),
                    "status": "implemented",
                }
            )

    powershell_files = sorted(
        [*_iter_files(REPO_ROOT, "*.ps1"), *_iter_files(REPO_ROOT, "*.psm1")], key=_relative
    )
    powershell_records = []
    for path in powershell_files:
        content = _safe_text(path)
        powershell_records.append(
            {
                "path": _relative(path),
                "functions": sorted(set(re.findall(r"(?im)^function\s+([A-Za-z0-9_-]+)", content))),
                "status": _status_for_source(path, content),
            }
        )

    skill_files = sorted(_iter_files(REPO_ROOT, "SKILL.md"), key=_relative)
    skill_records = [
        {
            "name": path.parent.name.replace("-", "_"),
            "path": _relative(path),
            "tracked": bool(_git("ls-files", "--error-unmatch", _relative(path), check=False)),
            "status": "implemented" if _safe_text(path).strip() else "stub",
        }
        for path in skill_files
    ]
    rule_router = AGENT_ROOT / "src/ultrafast_memory/chat/router/rule_router.py"
    router_text = _safe_text(rule_router)
    runtime_skills = sorted(
        set(
            re.findall(
                r'"(task_intake|process_file_ingestion|bo_dataset_governance|bo_recommendation|crl_task_planning|rag_literature_retrieval|experience_memory_update|report_generation|knowledge_bootstrap|expert_review)"',
                router_text,
            )
        )
    )

    service_files = sorted(
        [path for path in python_files if path.name.endswith("service.py")], key=_relative
    )
    tool_references = sorted(set(re.findall(r'allowed_tools=\[([^\]]*)\]', router_text)))
    tool_names = sorted(set(re.findall(r'"([a-z][a-z0-9_]+)"', " ".join(tool_references))))

    migration_files = sorted(
        path
        for path in _iter_files(REPO_ROOT)
        if "migration" in path.name.lower() or "migrations" in {part.lower() for part in path.parts}
    )
    config_files = sorted(
        path
        for path in _iter_files(REPO_ROOT)
        if path.suffix.lower() in {".yaml", ".yml", ".toml"}
        or path.name in {"requirements.txt", "llm.local.json", ".gitignore"}
    )
    test_files = sorted(
        path for path in python_files if path.name.startswith("test_") or path.name == "conftest.py"
    )

    db_tables = []
    init_db = AGENT_ROOT / "src/ultrafast_memory/db/init_db.py"
    for table in sorted(set(re.findall(r"(?i)CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)", _safe_text(init_db)))):
        db_tables.append(
            {"name": table, "source": _relative(init_db), "status": "implemented"}
        )

    return {
        "python_files": python_records,
        "python_file_count": len(python_records),
        "entrypoints": entrypoints,
        "api_endpoints": sorted(api_endpoints, key=lambda item: (item["path"] or "", item["method"])),
        "cli_commands": cli_commands,
        "powershell_tui": powershell_records,
        "skills": skill_records,
        "runtime_skill_names": runtime_skills,
        "tools": {
            "formal_registry_status": "not_found",
            "router_declared_tools": tool_names,
            "overall_status": "partial",
        },
        "services": [
            {"path": _relative(path), "status": _status_for_source(path, _safe_text(path))}
            for path in service_files
        ],
        "database_models": {
            "sqlalchemy_classes": db_model_classes,
            "sqlite_tables_declared": db_tables,
            "access_layer_status": "partial",
        },
        "migrations": {
            "status": "implemented" if migration_files else "not_found",
            "files": [_relative(path) for path in migration_files],
            "note": "Current schema is created by init_db.py; no versioned migration framework was found.",
        },
        "configs": [
            {
                "path": _relative(path),
                "status": "local_only_ignored" if path.name == "llm.local.json" else "implemented",
            }
            for path in config_files
        ],
        "tests": {
            "files": [_relative(path) for path in test_files],
            "file_count": len(test_files),
            "test_function_count": test_function_count,
            "status": "implemented",
        },
    }


def _status_records() -> dict[str, list[str]]:
    lines = _git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
    records: dict[str, list[str]] = {
        "modified": [],
        "added": [],
        "deleted": [],
        "renamed": [],
        "untracked": [],
        "other": [],
    }
    for line in lines:
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            records["untracked"].append(path)
        elif "D" in code:
            records["deleted"].append(path)
        elif "R" in code:
            records["renamed"].append(path)
        elif "A" in code:
            records["added"].append(path)
        elif "M" in code:
            records["modified"].append(path)
        else:
            records["other"].append(f"{code} {path}")
    return records


def collect_repository_inventory(code_inventory: dict[str, Any]) -> dict[str, Any]:
    ignored_candidates = [
        "ultrafast_laser_memory/data",
        "ultrafast_laser_memory/超快智能体文献检索",
        "ultrafast_laser_memory/configs/llm.local.json",
        "ultrafast_laser_memory/configs/secrets",
        "outputs/run_log.txt",
        ".pytest_cache",
        "ultrafast_laser_memory/.pytest_cache",
    ]
    ignored = []
    for value in ignored_candidates:
        path = REPO_ROOT / value
        ignored.append(
            {
                "path": value,
                "exists": path.exists(),
                "ignored": bool(_git("check-ignore", value, check=False)),
            }
        )
    local_branches = [line for line in _git("branch", "--format=%(refname:short)|%(objectname)|%(upstream:short)").splitlines() if line]
    remote_branches = [line for line in _git("branch", "-r", "--format=%(refname:short)|%(objectname)").splitlines() if line]
    remotes = []
    for line in _git("remote", "-v").splitlines():
        parts = line.split()
        if len(parts) >= 3:
            remotes.append({"name": parts[0], "url": parts[1], "direction": parts[2].strip("()")})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(REPO_ROOT),
        "git": {
            "remotes": remotes,
            "current_branch": _git("branch", "--show-current"),
            "head_commit": _git("rev-parse", "HEAD"),
            "head_summary": _git("show", "-s", "--format=%h %s", "HEAD"),
            "local_branches": local_branches,
            "remote_branches": remote_branches,
            "tags": _git("tag", "--list").splitlines(),
            "working_tree": _status_records(),
            "ignored_key_paths": ignored,
        },
        "project_roots": [
            {
                "path": ".",
                "kind": "legacy_bo_python_project",
                "evidence": ["main.py", "requirements.txt", "src/", "tests/"],
                "status": "implemented",
            },
            {
                "path": "ultrafast_laser_memory",
                "kind": "packaged_agent_memory_project",
                "evidence": ["pyproject.toml", "src/ultrafast_memory/", "tests/"],
                "status": "implemented",
            },
        ],
        "multiple_project_roots": True,
        "code_inventory": code_inventory,
    }


def _sqlite_inventory(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": _relative(path),
        "bytes": path.stat().st_size,
        "status": "implemented",
        "tables": {},
    }
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
            )
            if not row[0].startswith("sqlite_")
        ]
        for table in tables:
            try:
                quoted = table.replace('"', '""')
                result["tables"][table] = connection.execute(
                    f'SELECT COUNT(*) FROM "{quoted}"'
                ).fetchone()[0]
            except sqlite3.Error as exc:
                result["tables"][table] = {"error": type(exc).__name__}
        connection.close()
    except sqlite3.Error as exc:
        result["status"] = "partial"
        result["error"] = type(exc).__name__
    return result


def _area_inventory(path: Path) -> dict[str, Any]:
    files = list(_iter_files(path)) if path.exists() else []
    extensions = Counter((item.suffix.lower() or "<none>") for item in files)
    return {
        "path": _relative(path),
        "exists": path.exists(),
        "file_count": len(files),
        "bytes": sum(item.stat().st_size for item in files),
        "extensions": dict(sorted(extensions.items())),
    }


def _line_count(path: Path) -> int | None:
    if path.suffix.lower() not in {".jsonl", ".csv"}:
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def collect_data_inventory() -> dict[str, Any]:
    discovered_db_files = sorted(
        [
            path
            for suffix in ("*.db", "*.sqlite", "*.sqlite3")
            for path in _iter_files(REPO_ROOT, suffix)
        ],
        key=_relative,
    )
    live_db = AGENT_ROOT / "data/ultrafast_memory.db"
    db_files = ([live_db] if live_db in discovered_db_files else []) + [
        path for path in discovered_db_files if path != live_db
    ]
    cards = sorted(
        [path for path in _iter_files(REPO_ROOT) if "literature_card" in path.name.lower()],
        key=_relative,
    )
    candidate_files = sorted(
        [path for path in _iter_files(REPO_ROOT) if "knowledge_candidate" in path.name.lower()],
        key=_relative,
    )
    task_states = sorted(
        [path for path in _iter_files(REPO_ROOT, "*.json") if "task_state" in path.name.lower()],
        key=_relative,
    )
    logs = sorted(_iter_files(REPO_ROOT, "*.log"), key=_relative)
    report_files = sorted(
        [
            path
            for path in _iter_files(REPO_ROOT)
            if "report" in {part.lower() for part in path.parts}
            or "reports" in {part.lower() for part in path.parts}
            or "report" in path.name.lower()
        ],
        key=_relative,
    )
    csv_files = sorted(_iter_files(REPO_ROOT, "*.csv"), key=_relative)
    sqlite = [_sqlite_inventory(path) for path in db_files]
    for index, record in enumerate(sqlite):
        record["role"] = "live" if index == 0 and db_files[index] == live_db else "baseline_backup"
    primary_tables = sqlite[0]["tables"] if sqlite else {}

    sensitive_paths = [
        AGENT_ROOT / "configs/llm.local.json",
        AGENT_ROOT / "configs/secrets/DEEPSEEK_API_KEY.dpapi",
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sqlite_databases": sqlite,
        "primary_database": _relative(live_db) if live_db.exists() else None,
        "rag_indexes": {
            "rag_index_rows": primary_tables.get("rag_index", 0),
            "rag_index_entry_rows": primary_tables.get("rag_index_entry", 0),
            "fts_chunk_rows": primary_tables.get("literature_chunk_fts", 0),
            "status": "implemented" if primary_tables.get("rag_index_entry", 0) else "partial",
        },
        "literature": {
            "source_workspace": _area_inventory(AGENT_ROOT / "超快智能体文献检索"),
            "archive": _area_inventory(AGENT_ROOT / "data/literature_archive"),
            "pdf_total_repository": sum(1 for _ in _iter_files(REPO_ROOT, "*.pdf")),
            "paper_rows": primary_tables.get("literature_paper", 0),
            "section_rows": primary_tables.get("literature_section", 0),
            "chunk_rows": primary_tables.get("literature_chunk", 0),
            "artifact_rows": primary_tables.get("literature_artifact", 0),
        },
        "literature_cards": [
            {"path": _relative(path), "bytes": path.stat().st_size, "rows": _line_count(path)}
            for path in cards
        ],
        "knowledge_candidates": {
            "database_rows": primary_tables.get("knowledge_candidate", 0),
            "files": [
                {"path": _relative(path), "bytes": path.stat().st_size, "rows": _line_count(path)}
                for path in candidate_files
            ],
        },
        "review_tasks": {
            "database_rows": primary_tables.get("knowledge_review_task", 0),
            "review_action_rows": primary_tables.get("knowledge_review_action", 0),
        },
        "equipment_profiles": {
            "profile_rows": primary_tables.get("equipment_profile", 0),
            "revision_rows": primary_tables.get("equipment_config_revision", 0),
            "status": "implemented" if primary_tables.get("equipment_profile", 0) else "partial",
        },
        "bo_datasets": {
            "training_sample_rows": primary_tables.get("bo_training_sample", 0),
            "csv_files": [
                {"path": _relative(path), "bytes": path.stat().st_size, "lines": _line_count(path)}
                for path in csv_files
            ],
        },
        "task_state_files": [
            {"path": _relative(path), "bytes": path.stat().st_size} for path in task_states
        ],
        "logs": [{"path": _relative(path), "bytes": path.stat().st_size} for path in logs],
        "reports": [{"path": _relative(path), "bytes": path.stat().st_size} for path in report_files],
        "data_areas": [
            _area_inventory(REPO_ROOT / "data"),
            _area_inventory(REPO_ROOT / "inputs"),
            _area_inventory(REPO_ROOT / "outputs"),
            _area_inventory(AGENT_ROOT / "data"),
        ],
        "sensitive_artifacts": [
            {
                "path": _relative(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "content_inspected": False,
                "git_ignored": bool(_git("check-ignore", _relative(path), check=False)),
            }
            for path in sensitive_paths
        ],
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    code = collect_code_inventory()
    repository = collect_repository_inventory(code)
    data = collect_data_inventory()
    (REPORTS_DIR / "repository_inventory.json").write_text(
        json.dumps(repository, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS_DIR / "data_inventory.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "repository_inventory": _relative(REPORTS_DIR / "repository_inventory.json"),
                "data_inventory": _relative(REPORTS_DIR / "data_inventory.json"),
                "python_files": code["python_file_count"],
                "api_endpoints": len(code["api_endpoints"]),
                "cli_commands": len(code["cli_commands"]),
                "tests": code["tests"]["test_function_count"],
                "sqlite_databases": len(data["sqlite_databases"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
