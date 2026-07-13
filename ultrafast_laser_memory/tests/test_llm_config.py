from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ultrafast_memory.apps.api.main import app
from ultrafast_memory.core.llm_config import get_llm_config


def _clear_env(monkeypatch):
    for key in (
        "ULTRAFAST_LLM_PROVIDER",
        "ULTRAFAST_LLM_MODEL",
        "ULTRAFAST_LLM_API_BASE",
        "ULTRAFAST_LLM_API_KEY_ENV",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_llm_config_unconfigured(isolated_root, monkeypatch):
    _clear_env(monkeypatch)
    cfg = get_llm_config()
    assert cfg["provider"] is None
    assert cfg["api_key_available"] is False


def test_llm_config_from_environment(isolated_root, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ULTRAFAST_LLM_PROVIDER", "openai")
    monkeypatch.setenv("ULTRAFAST_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("ULTRAFAST_LLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("ULTRAFAST_LLM_API_KEY_ENV", "OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    cfg = get_llm_config()
    assert cfg["api_key_available"] is True
    assert "sk-test-secret" not in json.dumps(cfg)


def test_llm_config_from_local_file(isolated_root, monkeypatch):
    _clear_env(monkeypatch)
    path = isolated_root / "configs" / "llm.local.json"
    path.write_text(
        json.dumps(
            {
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "api_base": "https://api.openai.com/v1",
                "api_key_source": "env",
                "api_key_env": "OPENAI_API_KEY",
            }
        ),
        encoding="utf-8",
    )
    cfg = get_llm_config()
    assert cfg["provider"] == "openai"
    assert cfg["api_key_env"] == "OPENAI_API_KEY"


def test_fastapi_llm_endpoints_do_not_expose_key(isolated_root, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ULTRAFAST_LLM_PROVIDER", "openai")
    monkeypatch.setenv("ULTRAFAST_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("ULTRAFAST_LLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("ULTRAFAST_LLM_API_KEY_ENV", "OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    client = TestClient(app)
    config_response = client.get("/llm/config")
    assert config_response.status_code == 200
    assert "sk-test-secret" not in config_response.text
    monkeypatch.setattr(
        "ultrafast_memory.llm.openai_compatible.OpenAICompatibleClient.test_connection",
        lambda self, **kwargs: {"ok": True},
    )
    test_response = client.post("/llm/test")
    assert test_response.status_code == 200
    assert test_response.json()["external_call_performed"] is True
    assert test_response.json()["valid"] is True
    assert "sk-test-secret" not in test_response.text
