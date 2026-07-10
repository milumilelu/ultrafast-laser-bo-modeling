from fastapi import APIRouter

router = APIRouter(prefix="/bo", tags=["bo"])


@router.post("/export")
def bo_export() -> dict:
    from ultrafast_memory.bo.dataset_builder import export_bo_dataset
    from ultrafast_memory.db.init_db import init_database

    init_database()
    return export_bo_dataset()
