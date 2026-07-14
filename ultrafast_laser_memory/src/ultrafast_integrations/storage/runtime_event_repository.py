from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_shared.db.unit_of_work import UnitOfWork


class RuntimeEventRepository:
    """Atomic durable store; ``run_id`` is the canonical event stream identifier."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def persist(
        self,
        event: AgentEvent,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        init_database(self.db_path)
        event.stream_id = event.run_id
        with UnitOfWork(self.db_path) as uow:
            assert uow.connection is not None
            existing = self._existing_idempotent(uow.connection, event)
            if existing is not None:
                uow.commit()
                record = self._row(dict(existing))
                self._hydrate_event(event, record)
                return {"event_id": event.event_id, **event.to_dict()}
            event.sequence = self._allocate_sequence(uow.connection, event.stream_id)
            self._insert_event(
                uow.connection,
                event,
                session_id=session_id or event.session_id,
                task_id=task_id or event.task_id,
            )
            uow.commit()
        return {"event_id": event.event_id, **event.to_dict()}

    @staticmethod
    def _existing_idempotent(
        connection: sqlite3.Connection, event: AgentEvent
    ) -> sqlite3.Row | None:
        if not event.idempotency_key:
            return None
        return connection.execute(
            "SELECT * FROM runtime_public_event WHERE stream_id=? AND idempotency_key=?",
            (event.stream_id, event.idempotency_key),
        ).fetchone()

    @staticmethod
    def _allocate_sequence(connection: sqlite3.Connection, stream_id: str) -> int:
        row = connection.execute(
            """INSERT INTO runtime_event_sequence(stream_id, next_sequence)
               VALUES (?, 2)
               ON CONFLICT(stream_id) DO UPDATE SET next_sequence=next_sequence+1
               RETURNING next_sequence-1""",
            (stream_id,),
        ).fetchone()
        assert row is not None
        return int(row[0])

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        event: AgentEvent,
        *,
        session_id: str | None,
        task_id: str | None,
    ) -> None:
        value = event.to_dict()
        connection.execute(
            """INSERT INTO runtime_public_event (
                event_id, run_id, session_id, task_id, sequence, event_type, stage,
                title, summary, status, progress, skill, tool, duration_ms, cache_hit,
                attempt, data_json, created_at, stream_id, idempotency_key
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.event_id,
                event.run_id,
                session_id,
                task_id,
                event.sequence,
                event.event_type,
                event.stage,
                event.title,
                event.summary,
                event.status,
                event.progress,
                event.skill,
                event.tool_name,
                event.duration_ms,
                None if event.cache_hit is None else int(event.cache_hit),
                event.attempt,
                json.dumps(
                    {
                        **(value.get("data") or {}),
                        "trace_id": value.get("trace_id"),
                        "input_summary": value.get("input_summary") or {},
                        "output_summary": value.get("output_summary") or {},
                        "evidence_refs": value.get("evidence_refs") or [],
                        "parent_event_id": value.get("parent_event_id"),
                        "visibility": value.get("visibility", "public"),
                        "workflow_id": value.get("workflow_id"),
                        "message_id": value.get("message_id"),
                        "step": value.get("step"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                event.timestamp,
                event.stream_id,
                event.idempotency_key,
            ),
        )

    @staticmethod
    def _hydrate_event(event: AgentEvent, record: dict[str, Any]) -> None:
        for key in (
            "event_id",
            "run_id",
            "stream_id",
            "idempotency_key",
            "sequence",
            "event_type",
            "stage",
            "title",
            "summary",
            "status",
            "progress",
            "skill",
            "duration_ms",
            "cache_hit",
            "attempt",
            "trace_id",
            "session_id",
            "task_id",
            "workflow_id",
            "message_id",
            "step",
            "visibility",
            "timestamp",
        ):
            if key in record:
                setattr(event, key, record[key])
        event.tool = record.get("tool")
        event.tool_name = record.get("tool_name")
        event.data = dict(record.get("data") or {})
        event.payload = dict(event.data)
        event.public_summary = event.summary
        event.input_summary = dict(record.get("input_summary") or {})
        event.output_summary = dict(record.get("output_summary") or {})
        event.evidence_refs = list(record.get("evidence_refs") or [])
        event.parent_event_id = record.get("parent_event_id")

    def max_sequence(self, run_id: str) -> int:
        init_database(self.db_path)
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT next_sequence-1 FROM runtime_event_sequence WHERE stream_id=?",
                (run_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        init_database(self.db_path)
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE run_id=? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    def list_task_events(self, task_id: str) -> list[dict[str, Any]]:
        init_database(self.db_path)
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE task_id=? ORDER BY created_at, sequence",
                (task_id,),
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    def list_session_events(self, session_id: str) -> list[dict[str, Any]]:
        init_database(self.db_path)
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE session_id=? "
                "ORDER BY created_at, sequence",
                (session_id,),
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    @staticmethod
    def _row(row: dict[str, Any]) -> dict[str, Any]:
        row["cache_hit"] = None if row["cache_hit"] is None else bool(row["cache_hit"])
        data = json.loads(row.pop("data_json") or "{}")
        for key in (
            "trace_id",
            "input_summary",
            "output_summary",
            "evidence_refs",
            "parent_event_id",
            "visibility",
            "workflow_id",
            "message_id",
            "step",
        ):
            if key in data:
                row[key] = data.pop(key)
        row["trace_id"] = row.get("trace_id") or row["run_id"]
        row["stream_id"] = row.get("stream_id") or row["run_id"]
        row["tool_name"] = row.get("tool")
        row["timestamp"] = row["created_at"]
        row["data"] = data
        return row
