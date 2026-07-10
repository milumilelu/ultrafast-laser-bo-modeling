from __future__ import annotations

from ultrafast_memory.llm.anthropic import AnthropicClient
from ultrafast_memory.llm.base import BaseLLMClient
from ultrafast_memory.llm.mock import MockLLMClient
from ultrafast_memory.llm.openai_compatible import OpenAICompatibleClient


OPENAI_COMPATIBLE_PROVIDERS = {"openai", "deepseek", "moonshot", "qwen", "glm", "local"}


def create_llm_client(config: dict | None) -> BaseLLMClient:
    if not config:
        return MockLLMClient()
    if not config.get("api_key_available"):
        return MockLLMClient()
    provider = config.get("provider")
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleClient(config)
    if provider == "anthropic":
        return AnthropicClient()
    return MockLLMClient()
