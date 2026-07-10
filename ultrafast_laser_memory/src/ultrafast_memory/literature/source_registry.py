from __future__ import annotations

from typing import Any

from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def register_literature_artifact(record: dict[str, Any]) -> dict[str, Any]:
    """Register an immutable source artifact without replacing an existing SHA/type pair."""
    init_database()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM literature_artifact WHERE sha256=? AND asset_type=?",
            (record["sha256"], record["asset_type"]),
        ).fetchone()
        if existing:
            return dict(existing)
        conn.execute(
            """
            INSERT INTO literature_artifact
            (artifact_id,original_path,archived_path,asset_type,sha256,file_size_bytes,parent_root,parse_status,parser_name,parser_version,error_message,discovered_at,imported_at)
            VALUES (:artifact_id,:original_path,:archived_path,:asset_type,:sha256,:file_size_bytes,:parent_root,:parse_status,:parser_name,:parser_version,:error_message,:discovered_at,:imported_at)
            """,
            record,
        )
        conn.commit()
        return record


def get_literature_artifact(artifact_id: str) -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM literature_artifact WHERE artifact_id=?", (artifact_id,)).fetchone()
    return dict(row) if row else None
