from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ultrafast_agent.observability import normalize_stream_event
from ultrafast_memory.chat.schemas import (
    ChatRequest,
    ChatResponse,
    CreateChatSessionRequest,
    CreateChatSessionResponse,
)


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatBootstrapRunRequest(BaseModel):
    query_intent: str = "find_literature_prior"
    max_sources: int = 5


@router.post("/sessions", response_model=CreateChatSessionResponse)
def create_chat_session(request: CreateChatSessionRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.chat.session_store import create_session

    init_database()
    session = create_session(request.title, request.mode)
    return {
        "session_id": session["session_id"],
        "title": session["title"],
        "mode": session["mode"],
        "created_at": session["created_at"],
    }


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.chat.service import handle_chat

    init_database()
    if request.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported in MVP")
    try:
        return handle_chat(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stream_ndjson")
def chat_stream_ndjson(request: ChatRequest) -> StreamingResponse:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.chat.service import handle_chat_stream_ndjson

    init_database()
    request.stream = True

    def iter_lines():
        for sequence, event in enumerate(handle_chat_stream_ndjson(request), start=1):
            normalized = normalize_stream_event(event, sequence, request.mode)
            if normalized is not None:
                yield json.dumps(normalized, ensure_ascii=False) + "\n"

    return StreamingResponse(iter_lines(), media_type="application/x-ndjson")


@router.get("/sessions/{session_id}/messages")
def chat_session_messages(session_id: str) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.chat.session_store import list_messages

    init_database()
    return {"session_id": session_id, "messages": list_messages(session_id)}


@router.get("/sessions/{session_id}/progress")
def chat_session_progress(session_id: str) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.agent_runtime.event_state_projector import EventStateProjector

    init_database()
    return {
        "session_id": session_id,
        "progress": EventStateProjector.session_progress(session_id),
        "thinking_status": EventStateProjector.public_status_events(session_id),
    }


@router.get("/sessions/{session_id}/thinking-status")
def chat_session_thinking_status(session_id: str) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.agent_runtime.event_state_projector import EventStateProjector

    init_database()
    return {"session_id": session_id, "events": EventStateProjector.public_status_events(session_id)}


@router.get("/sessions/{session_id}/agent-trace")
def chat_session_agent_trace(session_id: str, message_id: str | None = None) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.agent_runtime.trace_collector import list_agent_trace_events

    init_database()
    return {
        "session_id": session_id,
        "message_id": message_id,
        "events": list_agent_trace_events(session_id, message_id),
    }


@router.get("/sessions/{session_id}/knowledge-bootstrap")
def chat_session_knowledge_bootstrap(session_id: str) -> dict:
    from ultrafast_integrations.storage.read_models import get_session_bootstrap_read_model
    from ultrafast_memory.chat.session_state import get_session_state
    from ultrafast_memory.db.init_db import init_database

    init_database()
    state = get_session_state(session_id)
    active = state.get("active_knowledge_bootstrap") or {}
    accepted_ids = active.get("accepted_rag_doc_ids") or []
    read_model = get_session_bootstrap_read_model(
        state.get("pending_review_task_ids", []), accepted_ids
    )
    return {
        "session_id": session_id,
        "evidence_gap": state.get("evidence_gap") or {},
        "active_knowledge_bootstrap": active,
        "pending_review_tasks": read_model["pending_review_tasks"],
        "accepted_rag_documents": read_model["accepted_rag_documents"],
    }


@router.post("/sessions/{session_id}/knowledge-bootstrap/run")
def chat_session_knowledge_bootstrap_run(
    session_id: str, request: ChatBootstrapRunRequest
) -> dict:
    from ultrafast_memory.chat.session_state import get_session_state, update_session_state
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.knowledge_bootstrap.service import bootstrap_external_knowledge

    init_database()
    state = get_session_state(session_id)
    active = state.get("active_knowledge_bootstrap") or {}
    result = bootstrap_external_knowledge(
        task_spec=active.get("task_spec") or {},
        question=active.get("question"),
        query_intent=request.query_intent,
        max_sources=request.max_sources,
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
