from __future__ import annotations

import json

from ultrafast_memory.agent_runtime.trace_collector import list_agent_trace_events
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.migrations.legacy_trace import migrate_legacy_traces


def _seed_legacy_rows() -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO agent_trace_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "old-agent-1", "old-session", "old-message", "tool_result", "trial",
                "旧工具结果", "已完成旧工具调用", 50, "trial", "old_tool", None, None,
                "completed", "2025-01-01T00:00:01+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO reasoning_status_trace VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "old-reasoning-1", "old-session", "old-message", "old-workflow",
                "decision", "旧公开决策", "采用保守试切", json.dumps({"public": True}),
                "public", "2025-01-01T00:00:02+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO public_reasoning_trace VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "old-public-1", "old-run", 4, "review", "quality_review",
                "旧质量复核", "质量满足要求", json.dumps({"result": "pass"}),
                "2025-01-01T00:00:03+00:00",
            ),
        )
        connection.commit()


def test_legacy_trace_backfill_is_dry_runnable_resumable_and_idempotent(isolated_root):
    init_database()
    _seed_legacy_rows()

    dry = migrate_legacy_traces(dry_run=True)
    assert dry["legacy_rows"] == dry["converted_rows"] == 3
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runtime_public_event").fetchone()[0] == 0

    first = migrate_legacy_traces(resume=True, verify=True)
    second = migrate_legacy_traces(resume=True, verify=True)
    assert first["converted_rows"] == 3
    assert first["conflicts"] == []
    assert first["verification_result"]["passed"] is True
    assert second["converted_rows"] == 0
    assert second["skipped_rows"] == 3
    with get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runtime_public_event").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM legacy_trace_migration").fetchone()[0] == 3


def test_legacy_api_falls_back_only_when_canonical_history_is_absent(isolated_root):
    init_database()
    _seed_legacy_rows()

    fallback = list_agent_trace_events("old-session")
    assert len(fallback) == 2
    assert all(item["legacy_fallback"] is True for item in fallback)

    migrate_legacy_traces()
    canonical = list_agent_trace_events("old-session")
    assert len(canonical) == 2
    assert not any(item.get("legacy_fallback") for item in canonical)


def test_formal_modules_cannot_import_legacy_runtime_or_projection(project_root):
    roots = [
        project_root / "src/ultrafast_agent",
        project_root / "src/ultrafast_bo",
        project_root / "src/ultrafast_memory/process_workflow",
    ]
    forbidden = (
        "ultrafast_memory.agent_runtime",
        "ultrafast_memory.chat.legacy_projection_adapter",
        "ultrafast_memory.chat.legacy_status_parser",
    )
    violations = []
    for root in roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    violations.append(f"{path.relative_to(project_root)} imports {token}")
    assert violations == []


def test_formal_orchestrator_does_not_branch_on_substatus(project_root):
    source = (
        project_root / "src/ultrafast_memory/process_workflow/chat_orchestrator.py"
    ).read_text(encoding="utf-8")
    assert 'workflow.get("substatus") in' not in source
    assert 'state = workflow["substatus"]' not in source
    assert "legacy_projection_adapter" not in source
    assert "agent_runtime.trace_collector" not in source
