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
from ultrafast_memory.literature.service import (
    get_paper,
    ingest_literature,
    inventory_literature,
    list_papers,
)
from ultrafast_memory.rag.index_service import (
    create_index,
    ensure_index,
    get_index_by_name,
    get_index_status,
    index_pending_chunks,
)
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.demo.service import DemoService
from ultrafast_memory.doctor.service import DoctorService

app = typer.Typer(no_args_is_help=True)
literature_app = typer.Typer(no_args_is_help=True, help="Inventory and ingest literature assets.")
rag_app = typer.Typer(no_args_is_help=True, help="Create, update, and query literature RAG indexes.")
app.add_typer(literature_app, name="literature")
app.add_typer(rag_app, name="rag")


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


@literature_app.command("inventory")
def literature_inventory(root: str = typer.Option(..., "--root")) -> None:
    typer.echo(json.dumps(inventory_literature(root), ensure_ascii=False, indent=2))


@literature_app.command("ingest")
def literature_ingest(
    root: str = typer.Option(..., "--root"),
    mode: str = typer.Option("auto", "--mode"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    typer.echo(json.dumps(ingest_literature(root, mode, force), ensure_ascii=False, indent=2))


@literature_app.command("list")
def literature_list(limit: int = typer.Option(100, "--limit")) -> None:
    typer.echo(json.dumps(list_papers(limit=limit), ensure_ascii=False, indent=2))


@literature_app.command("show")
def literature_show(paper_id: str) -> None:
    try:
        typer.echo(json.dumps(get_paper(paper_id), ensure_ascii=False, indent=2))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@rag_app.command("create-index")
def rag_create_index(
    name: str = typer.Option("literature_default", "--name"),
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    dimension: int | None = typer.Option(None, "--dimension"),
) -> None:
    result = create_index({
        "index_name": name,
        "embedding_provider": provider,
        "embedding_model": model,
        "embedding_dimension": dimension,
    })
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@rag_app.command("index")
def rag_index_chunks(
    name: str = typer.Option("literature_default", "--name"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    index = ensure_index(name)
    typer.echo(json.dumps(index_pending_chunks(index["index_id"], force), ensure_ascii=False, indent=2))


@rag_app.command("status")
def rag_status(name: str = typer.Option("literature_default", "--name")) -> None:
    index = get_index_by_name(name)
    if not index:
        raise typer.BadParameter(f"index not found: {name}")
    typer.echo(json.dumps(get_index_status(index["index_id"]), ensure_ascii=False, indent=2))


@rag_app.command("query")
def rag_query(
    query: str,
    name: str = typer.Option("literature_default", "--name"),
    filters: str = typer.Option("{}", "--filters"),
    top_k: int = typer.Option(8, "--top-k"),
    purpose: str = typer.Option("literature_background", "--purpose"),
) -> None:
    try:
        parsed_filters = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid --filters JSON: {exc}") from exc
    typer.echo(json.dumps(query_rag({"query": query, "filters": parsed_filters, "top_k": top_k, "purpose": purpose, "index_name": name}), ensure_ascii=False, indent=2))


@app.command("doctor")
def doctor() -> None:
    result = DoctorService().run()
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "healthy":
        raise typer.Exit(code=1)


@app.command("demo-tgv")
def demo_tgv(
    approve_review: bool = typer.Option(
        False, "--approve-review", help="Explicitly approve the demo task review card."
    ),
) -> None:
    typer.echo(json.dumps(DemoService().run_tgv(approve_review), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
