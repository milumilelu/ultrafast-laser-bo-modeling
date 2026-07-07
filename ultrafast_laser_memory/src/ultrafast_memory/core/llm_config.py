from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ultrafast_memory.core.config import get_project_root, load_config


PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPUAI_API_KEY",
    "local": "OPENAI_API_KEY",
}

PROVIDER_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "anthropic": "https://api.anthropic.com",
    "moonshot": "https://api.moonshot.ai/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://api.z.ai/api/paas/v4",
    "local": "",
}


def _configured(provider: str | None, model: str | None, api_base: str | None, api_key_env: str | None) -> dict[str, Any]:
    key_env = api_key_env or (PROVIDER_KEY_ENV.get(provider or "") if provider else None)
    return {
        "provider": provider,
        "model": model,
        "api_base": api_base,
        "api_key_env": key_env,
        "api_key_available": bool(key_env and os.environ.get(key_env)),
    }


def _load_local_config(root: Path) -> dict[str, Any]:
    path = root / "configs" / "llm.local.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("api_key", None)
    return data


def get_llm_config(root: Path | None = None) -> dict[str, Any]:
    base = root or get_project_root()
    env_provider = os.environ.get("ULTRAFAST_LLM_PROVIDER")
    env_model = os.environ.get("ULTRAFAST_LLM_MODEL")
    env_base = os.environ.get("ULTRAFAST_LLM_API_BASE")
    env_key_env = os.environ.get("ULTRAFAST_LLM_API_KEY_ENV")
    if env_provider or env_model or env_base or env_key_env:
        provider = env_provider
        return _configured(
            provider,
            env_model,
            env_base or PROVIDER_BASE_URL.get(provider or ""),
            env_key_env,
        )

    local = _load_local_config(base)
    if local:
        provider = local.get("provider")
        return _configured(
            provider,
            local.get("model"),
            local.get("api_base") or PROVIDER_BASE_URL.get(provider or ""),
            local.get("api_key_env"),
        )

    default = load_config(base).get("llm", {})
    if default:
        provider = default.get("provider")
        return _configured(provider, default.get("model"), default.get("api_base"), default.get("api_key_env"))

    return {
        "provider": None,
        "model": None,
        "api_base": None,
        "api_key_env": None,
        "api_key_available": False,
    }
