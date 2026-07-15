from __future__ import annotations

import importlib.util
import os
import platform
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

from ultrafast_bo import BOStatusService
from ultrafast_bo.application.compatibility import LegacyBOCompatibilityAdapter
from ultrafast_memory.core.config import get_database_path, load_config
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.rag.index_service import get_index_by_name
from ultrafast_shared.db.migrations import BASELINE_MIGRATIONS, list_applied_migrations


class DoctorService:
    def run(self) -> dict[str, Any]:
        checks = [
            self._python(),
            self._dependencies(),
            self._config(),
            self._database(),
            self._write_access(),
            self._port(),
            self._equipment(),
            self._rag(),
            self._llm(),
            self._bo(),
            self._demo_fixtures(),
        ]
        failed = [item for item in checks if item["status"] == "fail"]
        warnings = [item for item in checks if item["status"] == "warning"]
        return {
            "status": "healthy" if not failed else "unhealthy",
            "readiness": "READY FOR DEMO" if not failed else "NOT READY FOR DEMO",
            "checks": checks,
            "failed_count": len(failed),
            "warning_count": len(warnings),
            "external_call_performed": False,
            "platform": platform.platform(),
        }

    def _python(self) -> dict[str, Any]:
        valid = sys.version_info >= (3, 10)
        return self._check("python", valid, sys.version.split()[0])

    def _dependencies(self) -> dict[str, Any]:
        packages = ("fastapi", "pydantic", "yaml", "numpy", "sklearn", "sqlalchemy", "uvicorn")
        missing = [name for name in packages if importlib.util.find_spec(name) is None]
        return {
            "name": "dependencies",
            "status": "pass" if not missing else "fail",
            "summary": "runtime dependencies importable" if not missing else "runtime dependencies missing",
            "details": {"checked": list(packages), "missing": missing},
        }

    def _config(self) -> dict[str, Any]:
        try:
            config = load_config()
            groups = sorted(config)
            required = {"app", "agent", "llm", "database", "equipment", "rag", "knowledge_review", "trial", "bo", "observability", "performance", "demo"}
            missing = sorted(required - set(groups))
            return {
                "name": "config",
                "status": "pass" if not missing else "warning",
                "summary": "configuration groups loaded",
                "details": {"groups": groups, "missing_groups": missing},
            }
        except Exception as exc:
            return self._failure("config", exc)

    def _database(self) -> dict[str, Any]:
        try:
            path = init_database()
            with get_connection() as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                applied = list_applied_migrations(connection)
                expected = [migration.migration_id for migration in BASELINE_MIGRATIONS]
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
            required_tables = {
                "trial_plan",
                "knowledge_usage_decision",
                "runtime_public_event",
                "task_report",
            }
            valid = integrity == "ok" and applied == expected and required_tables.issubset(tables)
            return {
                "name": "database",
                "status": "pass" if valid else "fail",
                "summary": "SQLite integrity and migrations",
                "details": {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "integrity_check": integrity,
                    "applied_migrations": applied,
                    "expected_migrations": expected,
                    "missing_required_tables": sorted(required_tables - tables),
                },
            }
        except Exception as exc:
            return self._failure("database", exc)

    def _write_access(self) -> dict[str, Any]:
        try:
            directory = get_database_path().parent
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="doctor-", dir=directory, delete=True):
                pass
            return self._check("write_access", True, "database directory is writable")
        except Exception as exc:
            return self._failure("write_access", exc)

    def _port(self) -> dict[str, Any]:
        config = load_config()
        host = str(config.get("app", {}).get("api_host", "127.0.0.1"))
        port = int(config.get("app", {}).get("api_port", 8000))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((host, port))
            return {
                "name": "port",
                "status": "pass",
                "summary": "configured API port is available",
                "details": {"host": host, "port": port},
            }
        except OSError as exc:
            return {
                "name": "port",
                "status": "warning",
                "summary": "configured API port is already in use",
                "details": {"host": host, "port": port, "error_type": type(exc).__name__},
            }

    def _equipment(self) -> dict[str, Any]:
        try:
            equipment = build_machine_bounds()
            ready = bool(equipment.get("active")) and not equipment.get("missing_equipment_fields")
            return {
                "name": "equipment",
                "status": "pass" if ready else "warning",
                "summary": "active equipment bounds" if ready else "equipment setup is incomplete",
                "details": {
                    "active": bool(equipment.get("active")),
                    "revision_id": equipment.get("revision_id"),
                    "missing_fields": equipment.get("missing_equipment_fields") or [],
                },
            }
        except Exception as exc:
            return self._failure("equipment", exc)

    def _rag(self) -> dict[str, Any]:
        try:
            rag_config = load_config().get("rag", {})
            name = str(rag_config.get("default_index_name") or "literature_default")
            configured_embedding = rag_config.get("embedding") or {}
            configured_provider = str(configured_embedding.get("provider") or "mock")
            configured_model = str(
                configured_embedding.get("model") or "deterministic-mock-v1"
            )
            provider_available = _embedding_runtime_available(
                configured_provider, configured_embedding
            )
            model_available = _embedding_model_available(
                configured_provider, configured_model, configured_embedding
            )
            index = get_index_by_name(name)
            if not index:
                return {
                    "name": "rag",
                    "status": "warning",
                    "summary": f"{name} index not found",
                    "details": {
                        "configured_provider": configured_provider,
                        "configured_model": configured_model,
                        "embedding_runtime_available": provider_available,
                        "embedding_model_available": model_available,
                    },
                }
            with get_connection() as connection:
                indexed = connection.execute(
                    "SELECT COUNT(*) FROM rag_index_entry WHERE index_id=? AND status='indexed'",
                    (index["index_id"],),
                ).fetchone()[0]
                lexical = connection.execute(
                    "SELECT COUNT(*) FROM rag_index_entry WHERE index_id=? AND status='lexical_indexed'",
                    (index["index_id"],),
                ).fetchone()[0]
                active = connection.execute(
                    "SELECT COUNT(*) FROM literature_chunk WHERE active=1"
                ).fetchone()[0]
                unindexed_reviewed = connection.execute(
                    """
                    SELECT COUNT(*) FROM rag_document d
                    JOIN knowledge_candidate c ON c.candidate_id=d.candidate_id
                    WHERE c.review_status IN ('accepted_to_rag','accepted_as_literature_evidence')
                      AND d.indexed=0
                    """
                ).fetchone()[0]
            provider_matches = (
                index.get("embedding_provider") == configured_provider
                and index.get("embedding_model") == configured_model
            )
            production_embedding = index.get("embedding_provider") != "mock"
            pending = max(0, int(active) - int(indexed) - int(lexical))
            ready = (
                indexed > 0
                and pending == 0
                and unindexed_reviewed == 0
                and provider_matches
                and provider_available
                and model_available
                and production_embedding
                and index.get("status") == "ready"
            )
            return {
                "name": "rag",
                "status": "pass" if ready else "warning",
                "summary": "production RAG index ready" if ready else "RAG index requires attention",
                "details": {
                    "index_id": index["index_id"],
                    "index_status": index.get("status"),
                    "embedding_provider": index.get("embedding_provider"),
                    "embedding_model": index.get("embedding_model"),
                    "configured_provider": configured_provider,
                    "configured_model": configured_model,
                    "provider_matches_config": provider_matches,
                    "embedding_runtime_available": provider_available,
                    "embedding_model_available": model_available,
                    "mock_embedding": not production_embedding,
                    "vector_entry_count": indexed,
                    "lexical_only_entry_count": lexical,
                    "active_chunk_count": active,
                    "pending_chunk_count": pending,
                    "unindexed_reviewed_document_count": unindexed_reviewed,
                },
            }
        except Exception as exc:
            return self._failure("rag", exc)

    def _llm(self) -> dict[str, Any]:
        try:
            config = get_llm_config()
            configured = bool(config.get("provider") and config.get("model"))
            return {
                "name": "llm",
                "status": "pass" if configured else "warning",
                "summary": "LLM configured" if configured else "MockLLM offline fallback will be used",
                "details": {
                    "provider": config.get("provider") or "mock",
                    "model": config.get("model") or "deterministic-mock",
                    "api_key_available": bool(config.get("api_key_available")),
                    "external_call_performed": False,
                },
            }
        except Exception as exc:
            return self._failure("llm", exc)

    def _bo(self) -> dict[str, Any]:
        try:
            status = BOStatusService().status_for_count(0).value
            result = LegacyBOCompatibilityAdapter().recommend(
                {},
                [],
                {
                    "active": True,
                    "revision_id": "doctor-smoke",
                    "machine_bounds": {"laser_power_W": [1, 2], "frequency_kHz": [50, 100]},
                },
            )
            valid = status == "rule_based_cold_start" and result["model_status"] == status
            return {
                "name": "bo",
                "status": "pass" if valid else "fail",
                "summary": "BO application service is connected",
                "details": {"cold_start_status": status, "bo_invoked": result["bo_invoked"], "adapter_placeholder": False},
            }
        except Exception as exc:
            return self._failure("bo", exc)

    def _demo_fixtures(self) -> dict[str, Any]:
        try:
            init_database()
            with get_connection() as connection:
                fixture_exists = bool(
                    connection.execute(
                        "SELECT 1 FROM literature_chunk WHERE chunk_id='demo-chunk-tgv'"
                    ).fetchone()
                )
                literature_chunks = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM literature_chunk WHERE active=1"
                    ).fetchone()[0]
                )
            return {
                "name": "demo_fixtures",
                "status": "pass",
                "summary": "TGV fixture ready" if fixture_exists else "TGV fixture will be provisioned deterministically",
                "details": {
                    "tgv_fixture_exists": fixture_exists,
                    "auto_provision_on_demo": True,
                    "active_literature_chunks": literature_chunks,
                    "external_network_required": False,
                },
            }
        except Exception as exc:
            return self._failure("demo_fixtures", exc)

    def _check(self, name: str, valid: bool, summary: str) -> dict[str, Any]:
        return {"name": name, "status": "pass" if valid else "fail", "summary": summary, "details": {}}

    def _failure(self, name: str, exc: Exception) -> dict[str, Any]:
        return {"name": name, "status": "fail", "summary": f"{type(exc).__name__}: {exc}", "details": {}}


def _embedding_runtime_available(provider: str, config: dict[str, Any]) -> bool:
    normalized = provider.strip().lower()
    if normalized == "mock":
        return True
    if normalized in {"sentence_transformers", "sentence-transformers", "local"}:
        return importlib.util.find_spec("sentence_transformers") is not None
    if normalized in {"openai_compatible", "openai-compatible", "openai"}:
        api_key_env = str(config.get("api_key_env") or "ULTRAFAST_EMBEDDING_API_KEY")
        base_url = str(config.get("base_url") or os.environ.get("ULTRAFAST_EMBEDDING_BASE_URL") or "")
        return bool(base_url and os.environ.get(api_key_env))
    return False


def _embedding_model_available(
    provider: str,
    model: str,
    config: dict[str, Any],
) -> bool:
    normalized = provider.strip().lower()
    if normalized == "mock":
        return True
    if normalized in {"openai_compatible", "openai-compatible", "openai"}:
        return _embedding_runtime_available(provider, config)
    if normalized not in {"sentence_transformers", "sentence-transformers", "local"}:
        return False
    candidates: list[Path] = []
    direct = Path(model).expanduser()
    if direct.exists():
        candidates.append(direct)
    slug = "models--" + model.replace("/", "--")
    hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    hub = Path(os.environ.get("HF_HUB_CACHE") or hf_home / "hub")
    candidates.append(hub / slug)
    sentence_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
    if sentence_home:
        candidates.extend([Path(sentence_home) / slug, Path(sentence_home) / model])
    weight_suffixes = {".safetensors", ".bin"}
    return any(
        path.is_file() and path.stat().st_size > 1024
        for candidate in candidates
        if candidate.exists()
        for path in candidate.rglob("*")
        if path.suffix.lower() in weight_suffixes
    )
