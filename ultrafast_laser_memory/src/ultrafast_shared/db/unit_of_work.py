from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from ultrafast_shared.db.session import get_connection


class UnitOfWork:
    """Small SQLite unit of work with explicit commit/rollback semantics."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None
        self._committed = False

    def __enter__(self) -> "UnitOfWork":
        self.connection = get_connection(self.db_path)
        self.connection.execute("BEGIN IMMEDIATE")
        return self

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("unit of work is not active")
        self.connection.commit()
        self._committed = True

    def rollback(self) -> None:
        if self.connection is not None:
            self.connection.rollback()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.connection is None:
            return
        try:
            if exc_type is not None or not self._committed:
                self.connection.rollback()
        finally:
            self.connection.close()
