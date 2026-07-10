from __future__ import annotations

import sqlite3
from pathlib import Path

from ultrafast_shared.config.loader import get_database_path


def get_connection(db_path: str | Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(db_path).resolve() if db_path else get_database_path()
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
    else:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection
