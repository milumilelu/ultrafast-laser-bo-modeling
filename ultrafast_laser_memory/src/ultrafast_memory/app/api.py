from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ultrafast_memory.agent_runtime.trace_collector import list_agent_trace_events
from ultrafast_memory.bo.dataset_builder import export_bo_dataset
from ultrafast_memory.chat.schemas import (
    ChatRequest,
    ChatResponse,
    CreateChatSessionRequest,
    CreateChatSessionResponse,
)
from ultrafast_memory.chat.session_state import get_session_state, update_session_state
from ultrafast_memory.chat.service import handle_chat, handle_chat_stream_ndjson
from ultrafast_memory.chat.session_store import create_session, list_messages
from ultrafast_memory.chat.workflow_status import get_latest_progress, list_public_thinking_status
from ultrafast_memory.core.llm_config import get_llm_config
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.equipment.bounds import build_machine_bounds
from ultrafast_memory.equipment.schemas import EquipmentProfileCreate, EquipmentProfileUpdate
from ultrafast_memory.equipment.service import (
    activate_equipment_profile,
    create_equipment_profile,
    get_active_equipment_profile,
    list_equipment_profiles,
    update_equipment_profile,
)
from ultrafast_memory.ingestion.pipeline import scan_directory
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest, EvidenceGapRequest
from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge, bootstrap_from_web, check_evidence_gap
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest
from ultrafast_memory.knowledge_review.service import apply_action, get_task, list_candidates as list_knowledge_candidates
from ultrafast_memory.knowledge_review.service import list_tasks
from ultrafast_memory.rag.index_stub import index_rag_document
from ultrafast_memory.literature.service import (
    get_ingestion_status,
    get_paper,
    get_paper_chunks,
    ingest_literature,
    inventory_literature,
    list_papers,
)
from ultrafast_memory.rag.index_service import create_index, get_index_status, index_pending_chunks
from ultrafast_memory.rag.query_service import query_rag
from ultrafast_memory.rag.schemas import RagQueryRequest
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


class RagIndexRequest(BaseModel):
    candidate_ids: list[str] = []
    index_name: str = "default"


class ChatBootstrapRunRequest(BaseModel):
    query_intent: str = "find_literature_prior"
    max_sources: int = 5


class LiteratureRootRequest(BaseModel):
    root: str


class LiteratureIngestRequest(BaseModel):
    root: str
    mode: str = "auto"
    force: bool = False


class RagCreateIndexRequest(BaseModel):
    index_name: str = "literature_default"
    embedding_provider: str = "mock"
    embedding_model: str = "deterministic-mock-v1"
    embedding_dimension: int = 64


class RagRunIndexRequest(BaseModel):
    force: bool = False


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


@app.post("/equipment/profiles")
def equipment_profile_create(req: EquipmentProfileCreate) -> dict:
    init_database()
    try:
        return create_equipment_profile(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/equipment/active")
def equipment_active() -> dict:
    init_database()
    profile = get_active_equipment_profile()
    if not profile:
        return {"active": False, "message": "no active equipment profile"}
    return {"active": True, **profile}


@app.get("/equipment/profiles")
def equipment_profiles() -> list[dict]:
    init_database()
    return list_equipment_profiles()


@app.post("/equipment/profiles/{equipment_profile_id}/activate")
def equipment_profile_activate(equipment_profile_id: str) -> dict:
    init_database()
    try:
        return activate_equipment_profile(equipment_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/equipment/profiles/{equipment_profile_id}")
def equipment_profile_update(equipment_profile_id: str, req: EquipmentProfileUpdate) -> dict:
    init_database()
    try:
        return update_equipment_profile(equipment_profile_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/equipment/active/machine-bounds")
def equipment_active_machine_bounds() -> dict:
    init_database()
    result = build_machine_bounds()
    if not result.get("active"):
        return {"active": False, "machine_bounds": {}, "missing_equipment_fields": result.get("missing_equipment_fields", [])}
    return result


@app.get("/equipment/schema")
def equipment_schema() -> dict:
    return {
        "schema_version": 2,
        "required_setup_fields": [
            "wavelength_nm",
            "pulse_width_min_fs",
            "pulse_width_max_fs",
            "rated_max_power_W",
            "actual_max_power_W",
            "frequency_min_kHz",
            "frequency_max_kHz",
            "scan_speed_min_mm_s",
            "scan_speed_max_mm_s",
            "spot_diameter_um",
        ],
        "range_input_format": "min,max",
    }


@app.post("/chat/sessions", response_model=CreateChatSessionResponse)
def create_chat_session(req: CreateChatSessionRequest) -> dict:
    init_database()
    session = create_session(req.title, req.mode)
    return {
        "session_id": session["session_id"],
        "title": session["title"],
        "mode": session["mode"],
        "created_at": session["created_at"],
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    init_database()
    if req.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported in MVP")
    try:
        return handle_chat(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat/stream_ndjson")
def chat_stream_ndjson(req: ChatRequest) -> StreamingResponse:
    init_database()
    req.stream = True

    def iter_lines():
        for event in handle_chat_stream_ndjson(req):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(iter_lines(), media_type="application/x-ndjson")


@app.get("/chat/sessions/{session_id}/messages")
def chat_session_messages(session_id: str) -> dict:
    init_database()
    return {
        "session_id": session_id,
        "messages": list_messages(session_id),
    }


@app.get("/chat/sessions/{session_id}/progress")
def chat_session_progress(session_id: str) -> dict:
    init_database()
    return {
        "session_id": session_id,
        "progress": get_latest_progress(session_id),
        "thinking_status": list_public_thinking_status(session_id),
    }


@app.get("/chat/sessions/{session_id}/thinking-status")
def chat_session_thinking_status(session_id: str) -> dict:
    init_database()
    return {
        "session_id": session_id,
        "events": list_public_thinking_status(session_id),
    }


@app.get("/chat/sessions/{session_id}/agent-trace")
def chat_session_agent_trace(session_id: str, message_id: str | None = None) -> dict:
    init_database()
    return {
        "session_id": session_id,
        "message_id": message_id,
        "events": list_agent_trace_events(session_id, message_id),
    }


@app.post("/knowledge/evidence-gap")
def knowledge_evidence_gap(req: EvidenceGapRequest) -> dict:
    init_database()
    return check_evidence_gap(req).model_dump(mode="json")


@app.post("/knowledge/bootstrap-web")
def knowledge_bootstrap_web(req: BootstrapWebRequest) -> dict:
    init_database()
    return bootstrap_from_web(req).model_dump(mode="json")


@app.get("/knowledge/candidates")
def knowledge_candidates(status: str = "pending_review") -> list[dict]:
    init_database()
    return list_knowledge_candidates(status)


@app.get("/knowledge/review/tasks")
def knowledge_review_tasks(status: str = "pending_review") -> list[dict]:
    init_database()
    return list_tasks(status)


@app.get("/knowledge/review/tasks/{review_id}")
def knowledge_review_task(review_id: str) -> dict:
    init_database()
    try:
        return get_task(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/knowledge/review/tasks/{review_id}/action")
def knowledge_review_action(review_id: str, req: ReviewActionRequest) -> dict:
    init_database()
    try:
        return apply_action(review_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/rag/documents")
def rag_documents() -> list[dict]:
    init_database()
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM rag_document ORDER BY created_at DESC").fetchall()]


@app.post("/literature/inventory")
def literature_inventory(req: LiteratureRootRequest) -> dict:
    try:
        return inventory_literature(req.root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/literature/ingest")
def literature_ingest(req: LiteratureIngestRequest) -> dict:
    try:
        return ingest_literature(req.root, req.mode, req.force)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/literature/ingestion-jobs/{job_id}")
def literature_ingestion_job(job_id: str) -> dict:
    try:
        return get_ingestion_status(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/literature/papers")
def literature_papers(limit: int = 100, offset: int = 0) -> list[dict]:
    return list_papers(limit, offset)


@app.get("/literature/papers/{paper_id}")
def literature_paper(paper_id: str) -> dict:
    try:
        return get_paper(paper_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/literature/papers/{paper_id}/chunks")
def literature_paper_chunks(paper_id: str) -> list[dict]:
    return get_paper_chunks(paper_id)


@app.post("/rag/indexes")
def rag_create_index(req: RagCreateIndexRequest) -> dict:
    try:
        return create_index(req.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/rag/indexes/{index_id}/index")
def rag_run_index(index_id: str, req: RagRunIndexRequest) -> dict:
    try:
        return index_pending_chunks(index_id, req.force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/rag/indexes/{index_id}")
def rag_index_status(index_id: str) -> dict:
    try:
        return get_index_status(index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/rag/query")
def rag_query_endpoint(req: RagQueryRequest) -> dict:
    return query_rag(req)


@app.post("/rag/index")
def rag_index(req: RagIndexRequest) -> dict:
    init_database()
    jobs = []
    with get_connection() as conn:
        for candidate_id in req.candidate_ids:
            rows = conn.execute("SELECT rag_doc_id FROM rag_document WHERE candidate_id = ?", (candidate_id,)).fetchall()
            for row in rows:
                jobs.append(index_rag_document(row["rag_doc_id"], req.index_name))
    return {"jobs": jobs}


@app.get("/chat/sessions/{session_id}/knowledge-bootstrap")
def chat_session_knowledge_bootstrap(session_id: str) -> dict:
    init_database()
    state = get_session_state(session_id)
    active = state.get("active_knowledge_bootstrap") or {}
    accepted_ids = active.get("accepted_rag_doc_ids") or []
    with get_connection() as conn:
        pending = []
        for review_id in state.get("pending_review_task_ids", []):
            row = conn.execute("SELECT * FROM knowledge_review_task WHERE review_id = ?", (review_id,)).fetchone()
            if row:
                pending.append(dict(row))
        accepted = []
        for rag_doc_id in accepted_ids:
            row = conn.execute("SELECT * FROM rag_document WHERE rag_doc_id = ?", (rag_doc_id,)).fetchone()
            if row:
                accepted.append(dict(row))
    return {
        "session_id": session_id,
        "evidence_gap": state.get("evidence_gap") or {},
        "active_knowledge_bootstrap": active,
        "pending_review_tasks": pending,
        "accepted_rag_documents": accepted,
    }


@app.post("/chat/sessions/{session_id}/knowledge-bootstrap/run")
def chat_session_knowledge_bootstrap_run(session_id: str, req: ChatBootstrapRunRequest) -> dict:
    init_database()
    state = get_session_state(session_id)
    active = state.get("active_knowledge_bootstrap") or {}
    result = bootstrap_external_knowledge(
        task_spec=active.get("task_spec") or {},
        question=active.get("question"),
        query_intent=req.query_intent,
        max_sources=req.max_sources,
    )
    active.update(
        {
            "candidate_ids": result["candidate_ids"],
            "review_task_ids": result["review_task_ids"],
            "status": "pending_expert_review",
        }
    )
    update_session_state(
        session_id,
        {
            "active_knowledge_bootstrap": active,
            "pending_review_task_ids": result["review_task_ids"],
            "pending_bootstrap_permission": False,
        },
    )
    return {
        "executed": True,
        "candidate_ids": result["candidate_ids"],
        "review_task_ids": result["review_task_ids"],
        "next_action": "expert_review_required",
    }
