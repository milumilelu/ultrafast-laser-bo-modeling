from __future__ import annotations

import json
import uuid
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def create_session(title: str | None = None, mode: str = "agent") -> dict[str, Any]:
    init_database()
    now = utc_now_iso()
    session = {
        "session_id": stable_id("sess", title or "", mode, now),
        "title": title or "Untitled chat",
        "mode": mode,
        "created_at": now,
        "updated_at": now,
        "status": "active",
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_session VALUES (:session_id, :title, :mode, :created_at, :updated_at, :status)",
            session,
        )
        conn.commit()
    return session


def session_exists(session_id: str) -> bool:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM chat_session WHERE session_id = ?", (session_id,)).fetchone()
    return row is not None


def save_message(
    session_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role not in {"system", "user", "assistant", "tool"}:
        raise ValueError(f"invalid chat role: {role}")
    init_database()
    now = utc_now_iso()
    message = {
        "message_id": stable_id("msg", session_id, role, content, now, uuid.uuid4().hex),
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": now,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_message VALUES (:message_id, :session_id, :role, :content, :created_at, :metadata_json)",
            message,
        )
        conn.execute(
            "UPDATE chat_session SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
    return _message_view(message)


def get_recent_messages(session_id: str, limit: int = 20) -> list[dict[str, str]]:
    init_database()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM chat_message
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def list_messages(session_id: str) -> list[dict[str, Any]]:
    init_database()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chat_message
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [_message_view(dict(row)) for row in rows]


def save_skill_trace(session_id: str, message_id: str, route: dict[str, Any]) -> dict[str, Any]:
    init_database()
    now = utc_now_iso()
    trace = {
        "trace_id": stable_id("trace", session_id, message_id, route, now),
        "session_id": session_id,
        "message_id": message_id,
        "selected_skill": route.get("selected_skill"),
        "confidence": route.get("confidence"),
        "reason": route.get("reason"),
        "created_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_skill_trace VALUES (
                :trace_id, :session_id, :message_id, :selected_skill, :confidence, :reason, :created_at
            )
            """,
            trace,
        )
        conn.commit()
    return trace


def save_tool_trace(
    session_id: str,
    message_id: str,
    tool_name: str,
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    status: str = "not_called",
    error_message: str | None = None,
) -> dict[str, Any]:
    init_database()
    now = utc_now_iso()
    trace = {
        "trace_id": stable_id("tooltrace", session_id, message_id, tool_name, now),
        "session_id": session_id,
        "message_id": message_id,
        "tool_name": tool_name,
        "input_json": json.dumps(input_data or {}, ensure_ascii=False),
        "output_json": json.dumps(output_data or {}, ensure_ascii=False),
        "status": status,
        "created_at": now,
        "error_message": error_message,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_tool_trace VALUES (
                :trace_id, :session_id, :message_id, :tool_name, :input_json,
                :output_json, :status, :created_at, :error_message
            )
            """,
            trace,
        )
        conn.commit()
    return trace


def _message_view(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if metadata is None:
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}
    return {
        "message_id": row["message_id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "metadata": metadata,
    }
