from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ultrafast_memory.bo.dataset_builder import export_bo_dataset
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.ingestion.pipeline import scan_directory
from ultrafast_memory.knowledge.review_queue import (
    accept_candidate,
    list_candidates,
    mark_needs_more_evidence,
    reject_candidate,
)

app = FastAPI(title="Ultrafast Laser Memory MVP")


class ScanRequest(BaseModel):
    directory: str = "data/watch_dirs"


class ReviewRequest(BaseModel):
    action: str
    comment: str = ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ingest/scan")
def ingest_scan(req: ScanRequest) -> dict:
    init_database()
    return scan_directory(req.directory)


@app.get("/artifacts")
def artifacts() -> list[dict]:
    init_database()
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM raw_artifact ORDER BY imported_at DESC LIMIT 50")]


@app.get("/runs")
def runs() -> list[dict]:
    init_database()
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM process_run ORDER BY start_time DESC LIMIT 50")]


@app.get("/experience/candidates")
def candidates(status: str = "candidate") -> list[dict]:
    init_database()
    return list_candidates(status)


@app.post("/experience/candidates/{candidate_id}/review")
def review_candidate(candidate_id: str, req: ReviewRequest) -> dict:
    actions = {
        "accept": accept_candidate,
        "reject": reject_candidate,
        "needs_more_evidence": mark_needs_more_evidence,
    }
    if req.action not in actions:
        raise HTTPException(status_code=400, detail="invalid action")
    actions[req.action](candidate_id, req.comment)
    return {"candidate_id": candidate_id, "status": req.action}


@app.post("/bo/export")
def bo_export() -> dict:
    init_database()
    return export_bo_dataset()


@app.get("/llm/config")
def llm_config() -> dict:
    return get_llm_config()


@app.post("/llm/test")
def llm_test() -> dict:
    cfg = get_llm_config()
    configured = bool(cfg.get("provider") and cfg.get("model") and cfg.get("api_base") and cfg.get("api_key_available"))
    return {
        "configured": configured,
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "api_key_available": cfg.get("api_key_available"),
        "external_call_performed": False,
    }
