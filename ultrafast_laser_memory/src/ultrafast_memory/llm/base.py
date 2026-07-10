from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        raise NotImplementedError

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[dict]:
        result = self.chat(messages, **kwargs)
        yield {"type": "delta", "content": result.get("content", "")}
        yield {"type": "done"}
