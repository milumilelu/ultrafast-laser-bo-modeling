from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Migration:
    migration_id: str
    description: str
    statements: tuple[str, ...] = ()


BASELINE_MIGRATIONS = (
    Migration(
        migration_id="0001_baseline",
        description="Register the pre-refactor schema created by ultrafast_memory.db.init_db",
    ),
    Migration(
        migration_id="0002_trial_workflow",
        description="Add dual-mode trial planning, execution, result, and formal-process gate tables",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS trial_plan (
                trial_plan_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                trial_mode TEXT NOT NULL,
                representative_geometry_json TEXT NOT NULL,
                parameter_matrix_json TEXT NOT NULL,
                measurement_plan_json TEXT NOT NULL,
                acceptance_criteria_json TEXT NOT NULL,
                stop_conditions_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trial_execution (
                execution_id TEXT PRIMARY KEY,
                trial_plan_id TEXT NOT NULL,
                equipment_revision TEXT NOT NULL,
                actual_parameters_json TEXT NOT NULL,
                actual_path_json TEXT NOT NULL,
                monitoring_summary_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trial_result (
                result_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                measurements_json TEXT NOT NULL,
                defects_json TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                decision TEXT,
                reviewer_comment TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS formal_process_decision (
                formal_decision_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                trial_result_id TEXT,
                decision TEXT NOT NULL,
                unlocked INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_trial_plan_task ON trial_plan(task_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_trial_execution_plan ON trial_execution(trial_plan_id, started_at)",
            "CREATE INDEX IF NOT EXISTS idx_trial_result_execution ON trial_result(execution_id, created_at)",
        ),
    ),
    Migration(
        migration_id="0003_knowledge_use_gate",
        description="Add scoped knowledge-use decisions, approvals, reuse keys, and revocation",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS knowledge_usage_decision (
                decision_id TEXT PRIMARY KEY,
                session_id TEXT,
                task_id TEXT NOT NULL,
                intended_use TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                proposed_usage_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_usage_approval (
                approval_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                approval_scope TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                approved_payload_json TEXT NOT NULL,
                applicable_conditions_json TEXT NOT NULL,
                source_revision_hash TEXT NOT NULL,
                claim_revision_hash TEXT NOT NULL,
                equipment_revision TEXT NOT NULL,
                intended_use TEXT NOT NULL,
                approval_key TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_knowledge_usage_decision_task ON knowledge_usage_decision(task_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_usage_approval_key ON knowledge_usage_approval(approval_key, revoked_at)",
        ),
    ),
    Migration(
        migration_id="0004_runtime_observability",
        description="Add monotonic public runtime events with latency, retry, and cache metadata",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS runtime_public_event (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT,
                task_id TEXT,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                stage TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER,
                skill TEXT,
                tool TEXT,
                duration_ms REAL,
                cache_hit INTEGER,
                attempt INTEGER,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, sequence)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_runtime_event_session ON runtime_public_event(session_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_runtime_event_task ON runtime_public_event(task_id, created_at)",
        ),
    ),
    Migration(
        migration_id="0005_task_reports",
        description="Add auditable Markdown and JSON task-report records",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS task_report (
                report_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                run_id TEXT,
                markdown_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_task_report_task ON task_report(task_id, created_at)",
        ),
    ),
)


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
            migration_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def list_applied_migrations(connection: sqlite3.Connection) -> list[str]:
    _ensure_table(connection)
    return [
        row[0]
        for row in connection.execute(
            "SELECT migration_id FROM schema_migration ORDER BY migration_id"
        ).fetchall()
    ]


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Iterable[Migration] | None = None,
) -> list[str]:
    _ensure_table(connection)
    applied = set(list_applied_migrations(connection))
    newly_applied: list[str] = []
    ordered = sorted(migrations or BASELINE_MIGRATIONS, key=lambda item: item.migration_id)
    for migration in ordered:
        if migration.migration_id in applied:
            continue
        try:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migration VALUES (?, ?, ?)",
                (
                    migration.migration_id,
                    migration.description,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        newly_applied.append(migration.migration_id)
    return newly_applied
