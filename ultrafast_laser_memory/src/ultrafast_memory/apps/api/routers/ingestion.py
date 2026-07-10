from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ingestion"])


class ScanRequest(BaseModel):
    directory: str = "data/watch_dirs"


@router.post("/ingest/scan")
def ingest_scan(request: ScanRequest) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.ingestion.pipeline import scan_directory

    init_database()
    return scan_directory(request.directory)


@router.get("/artifacts")
def artifacts() -> list[dict]:
    from ultrafast_integrations.storage.read_models import list_artifacts

    return list_artifacts()


@router.get("/runs")
def runs() -> list[dict]:
    from ultrafast_integrations.storage.read_models import list_runs

    return list_runs()
