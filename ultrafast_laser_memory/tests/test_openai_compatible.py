from __future__ import annotations

import io
import urllib.error

import pytest

from ultrafast_memory.llm.openai_compatible import LLMProviderError, OpenAICompatibleClient


def _client(monkeypatch) -> OpenAICompatibleClient:
    monkeypatch.setenv("TEST_LLM_KEY", "test-secret-never-returned")
    return OpenAICompatibleClient(
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "api_base": "https://api.deepseek.com",
            "api_key_env": "TEST_LLM_KEY",
        }
    )


def test_http_auth_error_is_actionable_and_redacted(monkeypatch):
    client = _client(monkeypatch)
    body = b'{"error":{"message":"bad key test-secret-never-returned","code":"invalid_request_error"}}'

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(LLMProviderError) as raised:
        client.chat([{"role": "user", "content": "ping"}])

    assert raised.value.status_code == 401
    assert raised.value.error_code == "invalid_request_error"
    assert "API Key 无效或已撤销" in str(raised.value)
    assert "test-secret-never-returned" not in str(raised.value)


def test_stream_auth_error_preserves_safe_diagnostic(monkeypatch):
    client = _client(monkeypatch)

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    events = list(client.stream_chat([{"role": "user", "content": "ping"}]))

    assert events[0]["type"] == "error"
    assert events[0]["safe_to_display"] is True
    assert events[0]["status_code"] == 401
    assert "API Key 无效或已撤销" in events[0]["message"]
    assert events[-1] == {"type": "done"}


def test_capacity_error_is_actionable_and_redacted(monkeypatch):
    client = _client(monkeypatch)
    body = b'{"error":{"message":"Selected model is at capacity. Please try a different model."}}'

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("url", 503, "Unavailable", {}, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(LLMProviderError) as raised:
        client.chat([{"role": "user", "content": "ping"}])

    assert raised.value.status_code == 503
    assert raised.value.error_code == "model_capacity_exceeded"
    assert "容量已满" in str(raised.value)
