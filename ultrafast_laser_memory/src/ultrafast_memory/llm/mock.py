from __future__ import annotations

from typing import Any

from ultrafast_memory.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    provider = "mock"
    model = "mock"

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        last_user_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user_message = message.get("content", "")
                break
        return {
            "content": f"[MockLLM] 已收到：{last_user_message}",
            "raw": {},
            "provider": "mock",
            "model": "mock",
        }

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any):
        last_user_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user_message = message.get("content", "")
                break
        for chunk in ["[MockLLM] ", "已收到：", last_user_message]:
            yield {"type": "delta", "content": chunk}
        yield {"type": "done"}
