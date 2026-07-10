from fastapi import APIRouter

from ultrafast_memory.demo.schemas import DemoRunRequest


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/llm/config")
def llm_config() -> dict:
    from ultrafast_memory.core.llm_config import get_llm_config

    return get_llm_config()


@router.post("/llm/test")
def llm_test() -> dict:
    from ultrafast_memory.core.llm_config import get_llm_config

    config = get_llm_config()
    configured = bool(
        config.get("provider")
        and config.get("model")
        and config.get("api_base")
        and config.get("api_key_available")
    )
    return {
        "configured": configured,
        "provider": config.get("provider"),
        "model": config.get("model"),
        "api_key_available": config.get("api_key_available"),
        "external_call_performed": False,
    }


@router.get("/doctor")
def doctor() -> dict:
    from ultrafast_memory.doctor.service import DoctorService

    return DoctorService().run()


@router.post("/demo/tgv/run")
def demo_tgv_run(request: DemoRunRequest) -> dict:
    from ultrafast_memory.demo.service import DemoService

    return DemoService().run_tgv(request.approve_review)
