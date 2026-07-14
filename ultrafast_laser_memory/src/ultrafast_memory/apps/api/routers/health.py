from fastapi import APIRouter

from ultrafast_memory.demo.schemas import DemoRunRequest


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    from ultrafast_memory.core.runtime_identity import runtime_identity

    return {
        "status": "ok",
        "api_version": "0.3.0",
        "workflow_contract": "process-workflow-v3",
        "task_intake_contract": "agent-native-tools-v1",
        "runtime_identity": runtime_identity(),
    }


@router.get("/llm/config")
def llm_config() -> dict:
    from ultrafast_memory.core.llm_config import get_llm_config

    return get_llm_config()


@router.post("/llm/test")
def llm_test() -> dict:
    from ultrafast_memory.core.llm_config import get_llm_config
    from ultrafast_memory.llm.factory import create_llm_client
    from ultrafast_memory.llm.mock import MockLLMClient
    from ultrafast_memory.llm.openai_compatible import LLMProviderError

    config = get_llm_config()
    configured = bool(
        config.get("provider")
        and config.get("model")
        and config.get("api_base")
        and config.get("api_key_available")
    )
    result = {
        "configured": configured,
        "provider": config.get("provider"),
        "model": config.get("model"),
        "api_key_available": config.get("api_key_available"),
        "external_call_performed": False,
        "valid": False,
    }
    client = create_llm_client(config)
    if not configured or isinstance(client, MockLLMClient) or not hasattr(client, "test_connection"):
        result["message"] = "LLM 配置不完整，未执行外部验证。"
        return result
    result["external_call_performed"] = True
    try:
        client.test_connection(timeout=20)
        result["valid"] = True
        result["message"] = "LLM 凭证、接口和模型验证通过。"
    except LLMProviderError as exc:
        result["message"] = str(exc)
        result["status_code"] = exc.status_code
        result["error_code"] = exc.error_code
    return result


@router.get("/doctor")
def doctor() -> dict:
    from ultrafast_memory.doctor.service import DoctorService

    return DoctorService().run()


@router.post("/demo/tgv/run")
def demo_tgv_run(request: DemoRunRequest) -> dict:
    from ultrafast_memory.demo.service import DemoService

    return DemoService().run_tgv(request.approve_review, request.selected_trial_mode)
