from __future__ import annotations

import sqlite3

from ultrafast_memory.validation.bo_eligibility import evaluate_run


def check_run_quality(conn: sqlite3.Connection, run_id: str) -> list[str]:
    valid, reason = evaluate_run(conn, run_id)
    return [] if valid else [reason]
