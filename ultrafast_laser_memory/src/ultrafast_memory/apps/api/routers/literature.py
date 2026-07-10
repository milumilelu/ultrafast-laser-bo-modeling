from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/literature", tags=["literature"])


class LiteratureRootRequest(BaseModel):
    root: str


class LiteratureIngestRequest(BaseModel):
    root: str
    mode: str = "auto"
    force: bool = False


@router.post("/inventory")
def literature_inventory(request: LiteratureRootRequest) -> dict:
    from ultrafast_memory.literature.service import inventory_literature

    try:
        return inventory_literature(request.root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ingest")
def literature_ingest(request: LiteratureIngestRequest) -> dict:
    from ultrafast_memory.literature.service import ingest_literature

    try:
        return ingest_literature(request.root, request.mode, request.force)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ingestion-jobs/{job_id}")
def literature_ingestion_job(job_id: str) -> dict:
    from ultrafast_memory.literature.service import get_ingestion_status

    try:
        return get_ingestion_status(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/papers")
def literature_papers(limit: int = 100, offset: int = 0) -> list[dict]:
    from ultrafast_memory.literature.service import list_papers

    return list_papers(limit, offset)


@router.get("/papers/{paper_id}")
def literature_paper(paper_id: str) -> dict:
    from ultrafast_memory.literature.service import get_paper

    try:
        return get_paper(paper_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/papers/{paper_id}/chunks")
def literature_paper_chunks(paper_id: str) -> list[dict]:
    from ultrafast_memory.literature.service import get_paper_chunks

    return get_paper_chunks(paper_id)
