from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from ultrafast_agent.runtime.events import AgentEvent, redact_public_data
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


LEGACY_TRACE_TABLES = (
    ("agent_trace_event", "event_id"),
    ("reasoning_status_trace", "trace_id"),
    ("public_reasoning_trace", "trace_id"),
)


def migrate_legacy_traces(
    db_path: str | Path | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    resume: bool = False,
    verify: bool = True,
) -> dict[str, Any]:
    """Backfill old Trace rows into AgentEvent without changing or deleting source rows."""
    path = init_database(db_path)
    rows = list(_legacy_rows(path))
    selected = rows[:limit] if limit is not None else rows
    report: dict[str, Any] = {
        "legacy_rows": len(rows),
        "considered_rows": len(selected),
        "converted_rows": 0,
        "skipped_rows": 0,
        "conflicts": [],
        "dry_run": dry_run,
        "resume": resume,
    }
    repository = RuntimeEventRepository(path)
    for table, source_id, row in selected:
        if _ledger_entry(path, table, source_id):
            report["skipped_rows"] += 1
            continue
        try:
            event = _to_event(table, source_id, row)
            if not dry_run:
                repository.persist(event)
                _record_ledger(path, table, source_id, event.event_id)
            report["converted_rows"] += 1
        except Exception as exc:
            report["conflicts"].append({
                "source_table": table,
                "source_id": source_id,
                "reason": f"{type(exc).__name__}: {exc}",
            })
    report["verification_result"] = (
        _verify(path) if verify and not dry_run else "not_run"
    )
    return report


def legacy_session_fallback(
    session_id: str,
    message_id: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Historical-only reader used when a legacy API finds no canonical events."""
    path = init_database(db_path)
    result: list[dict[str, Any]] = []
    with get_connection(path, read_only=True) as connection:
        agent_rows = connection.execute(
            "SELECT * FROM agent_trace_event WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        reasoning_rows = connection.execute(
            "SELECT * FROM reasoning_status_trace WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    for row in [*agent_rows, *reasoning_rows]:
        value = dict(row)
        if message_id is not None and value.get("message_id") != message_id:
            continue
        source_id = str(value.get("event_id") or value.get("trace_id"))
        table = "agent_trace_event" if value.get("event_id") else "reasoning_status_trace"
        event = _to_event(table, source_id, value).to_dict()
        event["legacy_fallback"] = True
        result.append(event)
    return sorted(result, key=lambda item: (item.get("timestamp") or "", item["event_id"]))


def _legacy_rows(path: Path) -> Iterator[tuple[str, str, dict[str, Any]]]:
    with get_connection(path, read_only=True) as connection:
        for table, key in LEGACY_TRACE_TABLES:
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY {key}").fetchall()
            for row in rows:
                value = dict(row)
                yield table, str(value[key]), value


def _to_event(table: str, source_id: str, row: dict[str, Any]) -> AgentEvent:
    session_id = row.get("session_id")
    message_id = row.get("message_id")
    run_id = str(row.get("run_id") or stable_id(
        "legacy-agent-run", str(session_id or "unknown"), str(message_id or source_id)
    ))
    detail = _safe_json(
        row.get("detail_json") or row.get("trace_json"),
        {"legacy_source_table": table},
    )
    detail["legacy_source_table"] = table
    if row.get("sequence") is not None:
        detail["legacy_sequence"] = row["sequence"]
    return AgentEvent(
        event_id=f"legacy-{table}-{source_id}",
        run_id=run_id,
        sequence=0,
        event_type=str(row.get("event_type") or "legacy_trace"),
        stage=str(row.get("stage") or row.get("event_type") or "legacy"),
        title=str(row.get("title") or "历史 Trace"),
        summary=str(row.get("summary") or "历史公开执行记录"),
        status=str(row.get("status") or "completed"),
        session_id=session_id,
        message_id=message_id,
        workflow_id=row.get("workflow_id"),
        timestamp=str(row.get("created_at") or utc_now_iso()),
        progress=int(row["progress"]) if row.get("progress") is not None else None,
        skill=row.get("skill"),
        tool=row.get("tool"),
        visibility=str(row.get("visibility") or "public"),
        data=redact_public_data(detail),
        idempotency_key=f"legacy:{table}:{source_id}",
    )


def _safe_json(value: str | None, default: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return dict(default)
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return dict(default)
    return parsed if isinstance(parsed, dict) else dict(default)


def _ledger_entry(path: Path, table: str, source_id: str) -> bool:
    with get_connection(path, read_only=True) as connection:
        return connection.execute(
            "SELECT 1 FROM legacy_trace_migration WHERE source_table=? AND source_id=?",
            (table, source_id),
        ).fetchone() is not None


def _record_ledger(path: Path, table: str, source_id: str, event_id: str) -> None:
    with get_connection(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO legacy_trace_migration VALUES (?,?,?,?)",
            (table, source_id, event_id, utc_now_iso()),
        )
        connection.commit()


def _verify(path: Path) -> dict[str, Any]:
    with get_connection(path, read_only=True) as connection:
        ledger = connection.execute("SELECT COUNT(*) FROM legacy_trace_migration").fetchone()[0]
        canonical = connection.execute(
            "SELECT COUNT(*) FROM runtime_public_event WHERE idempotency_key LIKE 'legacy:%'"
        ).fetchone()[0]
        missing = connection.execute(
            """SELECT COUNT(*) FROM legacy_trace_migration m
               LEFT JOIN runtime_public_event e ON e.event_id=m.event_id
               WHERE e.event_id IS NULL"""
        ).fetchone()[0]
    return {
        "ledger_rows": ledger,
        "canonical_rows": canonical,
        "missing_canonical_rows": missing,
        "passed": ledger == canonical and missing == 0,
    }
