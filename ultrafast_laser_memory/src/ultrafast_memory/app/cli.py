from __future__ import annotations

import json

import typer

from ultrafast_memory.bo.dataset_builder import export_bo_dataset
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.ingestion.pipeline import scan_directory
from ultrafast_memory.knowledge.review_queue import (
    accept_candidate,
    list_candidates,
    mark_needs_more_evidence,
    reject_candidate,
)

app = typer.Typer(no_args_is_help=True)


@app.command("init-db")
def init_db() -> None:
    path = init_database()
    typer.echo(f"initialized: {path}")


@app.command("scan")
def scan(directory: str) -> None:
    typer.echo(json.dumps(scan_directory(directory), ensure_ascii=False, indent=2))


@app.command("list-artifacts")
def list_artifacts() -> None:
    init_database()
    with get_connection() as conn:
        for row in conn.execute("SELECT artifact_id, file_type, parse_status, file_path FROM raw_artifact ORDER BY imported_at DESC"):
            typer.echo(dict(row))


@app.command("list-runs")
def list_runs() -> None:
    init_database()
    with get_connection() as conn:
        for row in conn.execute("SELECT run_id, task_id, recipe_id, run_status, abnormal_flag FROM process_run ORDER BY start_time DESC"):
            typer.echo(dict(row))


@app.command("list-candidates")
def cli_list_candidates(status: str = "candidate") -> None:
    init_database()
    for row in list_candidates(status):
        typer.echo(row)


@app.command("review-candidate")
def review_candidate(candidate_id: str, action: str = typer.Option(...), comment: str = "") -> None:
    if action == "accept":
        accept_candidate(candidate_id, comment)
    elif action == "reject":
        reject_candidate(candidate_id, comment)
    elif action == "needs_more_evidence":
        mark_needs_more_evidence(candidate_id, comment)
    else:
        raise typer.BadParameter("action must be accept, reject, or needs_more_evidence")
    typer.echo(f"{candidate_id}: {action}")


@app.command("export-bo")
def export_bo() -> None:
    typer.echo(json.dumps(export_bo_dataset(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
