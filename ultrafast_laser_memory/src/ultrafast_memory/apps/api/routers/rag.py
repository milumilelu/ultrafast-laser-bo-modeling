from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ultrafast_memory.rag.schemas import RagQueryRequest


router = APIRouter(prefix="/rag", tags=["rag"])


class RagIndexRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    index_name: str = "literature_default"


class RagCreateIndexRequest(BaseModel):
    index_name: str = "literature_default"
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None


class RagRunIndexRequest(BaseModel):
    force: bool = False


@router.get("/documents")
def rag_documents() -> list[dict]:
    from ultrafast_integrations.storage.read_models import list_rag_documents

    return list_rag_documents()


@router.post("/indexes")
def rag_create_index(request: RagCreateIndexRequest) -> dict:
    from ultrafast_memory.rag.index_service import create_index

    try:
        return create_index(request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/indexes/{index_id}/index")
def rag_run_index(index_id: str, request: RagRunIndexRequest) -> dict:
    from ultrafast_memory.rag.index_service import index_pending_chunks

    try:
        return index_pending_chunks(index_id, request.force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/indexes/{index_id}")
def rag_index_status(index_id: str) -> dict:
    from ultrafast_memory.rag.index_service import get_index_status

    try:
        return get_index_status(index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/query")
def rag_query_endpoint(request: RagQueryRequest) -> dict:
    from ultrafast_memory.rag.query_service import query_rag

    return query_rag(request)


@router.post("/index")
def rag_index(request: RagIndexRequest) -> dict:
    from ultrafast_integrations.storage.read_models import find_candidate_rag_documents
    from ultrafast_memory.rag.index_service import index_rag_document

    jobs = []
    for candidate_id in request.candidate_ids:
        for rag_doc_id in find_candidate_rag_documents(candidate_id):
            jobs.append(index_rag_document(rag_doc_id, request.index_name))
    return {"jobs": jobs}
