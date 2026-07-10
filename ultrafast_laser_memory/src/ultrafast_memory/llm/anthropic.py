from __future__ import annotations

from typing import Any

from ultrafast_memory.llm.base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        raise NotImplementedError("Anthropic adapter is not implemented in MVP.")
