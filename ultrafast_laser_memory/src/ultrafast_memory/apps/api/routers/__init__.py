from ultrafast_memory.apps.api.routers.bo import router as bo_router
from ultrafast_memory.apps.api.routers.chat import router as chat_router
from ultrafast_memory.apps.api.routers.equipment import router as equipment_router
from ultrafast_memory.apps.api.routers.health import router as health_router
from ultrafast_memory.apps.api.routers.ingestion import router as ingestion_router
from ultrafast_memory.apps.api.routers.knowledge import router as knowledge_router
from ultrafast_memory.apps.api.routers.literature import router as literature_router
from ultrafast_memory.apps.api.routers.rag import router as rag_router
from ultrafast_memory.apps.api.routers.reports import router as reports_router
from ultrafast_memory.apps.api.routers.trial import router as trial_router
from ultrafast_memory.apps.api.routers.workflows import router as workflows_router


ROUTERS = (
    health_router,
    ingestion_router,
    equipment_router,
    chat_router,
    literature_router,
    rag_router,
    knowledge_router,
    trial_router,
    bo_router,
    workflows_router,
    reports_router,
)

__all__ = ["ROUTERS"]
