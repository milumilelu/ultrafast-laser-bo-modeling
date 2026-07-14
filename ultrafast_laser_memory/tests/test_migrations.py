from __future__ import annotations

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_shared.db.migrations import Migration, apply_migrations, list_applied_migrations


def test_baseline_migration_is_registered_and_idempotent(isolated_root):
    init_database()
    init_database()

    with get_connection() as connection:
        applied = list_applied_migrations(connection)
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migration WHERE migration_id='0001_baseline'"
        ).fetchone()[0]

    assert applied == [
        "0001_baseline",
        "0002_trial_workflow",
        "0003_knowledge_use_gate",
        "0004_runtime_observability",
            "0005_task_reports",
            "0006_process_workflow_v3",
            "0007_runtime_jobs_evolution",
            "0008_bo_governance_lifecycle",
            "0009_process_recommendation_cam_documents",
            "0010_atomic_runtime_event_sequence",
            "0011_legacy_trace_migration_ledger",
        ]
    assert count == 1


def test_custom_migration_is_atomic_and_idempotent(isolated_root):
    init_database()
    migration = Migration(
        "9999_test",
        "test migration",
        ("CREATE TABLE IF NOT EXISTS migration_test (id TEXT PRIMARY KEY)",),
    )
    with get_connection() as connection:
        first = apply_migrations(connection, [migration])
        second = apply_migrations(connection, [migration])
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migration WHERE migration_id='9999_test'"
        ).fetchone()[0]

    assert first == ["9999_test"]
    assert second == []
    assert count == 1
