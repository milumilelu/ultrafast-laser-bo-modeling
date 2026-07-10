from fastapi import FastAPI

from ultrafast_memory.apps.api.routers import ROUTERS


def create_app() -> FastAPI:
    application = FastAPI(title="Ultrafast Laser Agent", version="0.2.0")
    for router in ROUTERS:
        application.include_router(router)
    return application


app = create_app()
