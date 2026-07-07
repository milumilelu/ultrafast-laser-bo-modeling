from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from ultrafast_memory.core.file_type import detect_file_type
from ultrafast_memory.core.hashing import sha256_file
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso


def archive_artifact(file_path: str | Path, conn: sqlite3.Connection, raw_dir: str | Path) -> tuple[dict, bool]:
    path = Path(file_path).resolve()
    digest = sha256_file(path)
    existing = conn.execute("SELECT * FROM raw_artifact WHERE sha256 = ?", (digest,)).fetchone()
    if existing:
        return dict(existing), True

    today = utc_now_iso()[:10]
    archive_dir = Path(raw_dir) / today
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_path = archive_dir / f"{digest}_{path.name}"
    shutil.copy2(path, archived_path)
    stat = path.stat()
    artifact = {
        "artifact_id": stable_id("artifact", digest),
        "file_path": str(path),
        "archived_path": str(archived_path.resolve()),
        "file_type": detect_file_type(path),
        "sha256": digest,
        "file_size_bytes": stat.st_size,
        "created_at": None,
        "modified_at": utc_now_iso(),
        "imported_at": utc_now_iso(),
        "parser_name": None,
        "parser_version": None,
        "parse_status": "archived",
        "error_message": None,
    }
    conn.execute(
        """
        INSERT INTO raw_artifact VALUES (
          :artifact_id, :file_path, :archived_path, :file_type, :sha256,
          :file_size_bytes, :created_at, :modified_at, :imported_at,
          :parser_name, :parser_version, :parse_status, :error_message
        )
        """,
        artifact,
    )
    conn.commit()
    return artifact, False
