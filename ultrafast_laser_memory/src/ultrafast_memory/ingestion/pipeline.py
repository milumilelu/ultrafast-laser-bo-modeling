from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ultrafast_memory.core.config import get_project_root, resolve_path
from ultrafast_memory.core.file_type import detect_file_type
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.ingestion.archive import archive_artifact
from ultrafast_memory.ingestion.scanner import iter_supported_files
from ultrafast_memory.parsers.measurement_csv_parser import MeasurementCsvParser
from ultrafast_memory.parsers.operator_note_parser import OperatorNoteParser
from ultrafast_memory.parsers.recipe_json_parser import RecipeJsonParser
from ultrafast_memory.parsers.simple_log_parser import SimpleLogParser


PARSERS = {
    "json_recipe": RecipeJsonParser,
    "machine_log": SimpleLogParser,
    "measurement_csv": MeasurementCsvParser,
    "operator_note": OperatorNoteParser,
}


def _upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    keys = list(row)
    placeholders = ", ".join(f":{key}" for key in keys)
    columns = ", ".join(keys)
    updates = ", ".join(f"{key}=excluded.{key}" for key in keys if not key.endswith("_id"))
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT({keys[0]}) DO UPDATE SET {updates}",
        row,
    )


def _insert_parsed(conn: sqlite3.Connection, parsed: dict[str, Any], artifact_id: str) -> None:
    for row in parsed.get("tasks", []):
        _upsert(conn, "process_task", row)
    for row in parsed.get("recipes", []):
        row["artifact_id"] = artifact_id
        _upsert(conn, "process_recipe", row)
    for row in parsed.get("runs", []):
        row["artifact_id"] = artifact_id
        _upsert(conn, "process_run", row)
    for row in parsed.get("measurements", []):
        row["artifact_id"] = artifact_id
        _upsert(conn, "measurement_record", row)
    for row in parsed.get("experience_candidates", []):
        row["source_artifact_ids"] = row.get("source_artifact_ids") or json.dumps([artifact_id])
        _upsert(conn, "experience_candidate", row)


def ingest_file(file_path: str | Path, conn: sqlite3.Connection | None = None, raw_dir: str | Path | None = None) -> dict[str, Any]:
    close_conn = conn is None
    root = get_project_root()
    raw_path = raw_dir or resolve_path("data/raw_artifacts", root)
    init_database()
    db = conn or get_connection()
    try:
        artifact, skipped = archive_artifact(file_path, db, raw_path)
        if skipped:
            return {"imported": 0, "skipped": 1, "errors": []}
        file_type = detect_file_type(file_path)
        parser_cls = PARSERS.get(file_type)
        if not parser_cls:
            raise ValueError(f"unsupported file type: {file_type}")
        parser = parser_cls()
        parsed = parser.parse(str(file_path))
        _insert_parsed(db, parsed, artifact["artifact_id"])
        errors = parsed.get("errors", [])
        db.execute(
            "UPDATE raw_artifact SET parser_name=?, parser_version=?, parse_status=?, error_message=? WHERE artifact_id=?",
            (
                parser.name,
                parser.version,
                "parsed_with_warnings" if errors else "parsed",
                json.dumps(errors, ensure_ascii=False) if errors else None,
                artifact["artifact_id"],
            ),
        )
        db.commit()
        return {"imported": 1, "skipped": 0, "errors": errors}
    except Exception as exc:
        db.rollback()
        return {"imported": 0, "skipped": 0, "errors": [str(exc)]}
    finally:
        if close_conn:
            db.close()


def scan_directory(directory: str | Path) -> dict[str, Any]:
    init_database()
    totals: dict[str, Any] = {"imported": 0, "skipped": 0, "errors": []}
    with get_connection() as conn:
        for file_path in iter_supported_files(directory):
            result = ingest_file(file_path, conn=conn)
            totals["imported"] += result["imported"]
            totals["skipped"] += result["skipped"]
            totals["errors"].extend(result["errors"])
    return totals
