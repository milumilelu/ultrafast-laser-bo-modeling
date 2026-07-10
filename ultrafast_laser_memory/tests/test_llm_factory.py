from __future__ import annotations

from ultrafast_memory.llm.anthropic import AnthropicClient
from ultrafast_memory.llm.factory import create_llm_client
from ultrafast_memory.llm.mock import MockLLMClient
from ultrafast_memory.llm.openai_compatible import OpenAICompatibleClient


def test_llm_factory_returns_mock_for_missing_or_unavailable_config():
    assert isinstance(create_llm_client(None), MockLLMClient)
    assert isinstance(create_llm_client({"provider": "openai", "api_key_available": False}), MockLLMClient)


def test_llm_factory_returns_provider_clients_without_real_keys():
    cfg = {
        "provider": "openai",
        "model": "test-model",
        "api_base": "http://localhost:9999/v1",
        "api_key_env": "TEST_FAKE_API_KEY",
        "api_key_available": True,
    }
    assert isinstance(create_llm_client(cfg), OpenAICompatibleClient)
    assert isinstance(create_llm_client({"provider": "anthropic", "api_key_available": True}), AnthropicClient)
    assert isinstance(create_llm_client({"provider": "unknown", "api_key_available": True}), MockLLMClient)
