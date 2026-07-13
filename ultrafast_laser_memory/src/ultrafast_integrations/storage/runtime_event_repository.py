from __future__ import annotations

import json
from typing import Any

from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_shared.db.unit_of_work import UnitOfWork


class RuntimeEventRepository:
    def persist(
        self,
        event: AgentEvent,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        init_database()
        value = event.to_dict()
        event_id = event.event_id
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "INSERT INTO runtime_public_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    event.run_id,
                    session_id or event.session_id,
                    task_id or event.task_id,
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
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    event.timestamp,
                ),
            )
            uow.commit()
        return {"event_id": event_id, **value}

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        init_database()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE run_id=? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    def list_task_events(self, task_id: str) -> list[dict[str, Any]]:
        init_database()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE task_id=? ORDER BY created_at, sequence",
                (task_id,),
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    def list_session_events(self, session_id: str) -> list[dict[str, Any]]:
        init_database()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_public_event WHERE session_id=? "
                "ORDER BY created_at, sequence",
                (session_id,),
            ).fetchall()
        return [self._row(dict(row)) for row in rows]

    def _row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["cache_hit"] = None if row["cache_hit"] is None else bool(row["cache_hit"])
        data = json.loads(row.pop("data_json") or "{}")
        for key in (
            "trace_id",
            "input_summary",
            "output_summary",
            "evidence_refs",
            "parent_event_id",
            "visibility",
        ):
            if key in data:
                row[key] = data.pop(key)
        row["trace_id"] = row.get("trace_id") or row["run_id"]
        row["tool_name"] = row.get("tool")
        row["timestamp"] = row["created_at"]
        row["data"] = data
        return row
