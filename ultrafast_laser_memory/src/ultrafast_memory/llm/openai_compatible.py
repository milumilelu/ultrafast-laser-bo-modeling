from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from ultrafast_memory.llm.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, config: dict[str, Any]):
        self.provider = config.get("provider") or "openai"
        self.model = config.get("model") or ""
        self.api_base = (config.get("api_base") or "").rstrip("/")
        self.api_key_env = config.get("api_key_env") or ""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError("API key is not available in the configured environment variable")
        if not self.api_base:
            raise RuntimeError("api_base is not configured")
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=kwargs.get("timeout", 60)) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {detail[:500]}") from exc
        choices = raw.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
        return {
            "content": content,
            "raw": raw,
            "provider": self.provider,
            "model": self.model,
        }

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[dict]:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            yield {"type": "error", "message": "API key is not available in the configured environment variable"}
            yield {"type": "done"}
            return
        if not self.api_base:
            yield {"type": "error", "message": "api_base is not configured"}
            yield {"type": "done"}
            return
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "stream": True,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=kwargs.get("timeout", 60)) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        yield {"type": "done"}
                        return
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or choices[0].get("message") or {}
                    content = delta.get("content")
                    if content:
                        yield {"type": "delta", "content": content}
                yield {"type": "done"}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            yield {"type": "error", "message": f"LLM provider returned HTTP {exc.code}: {detail[:300]}"}
            yield {"type": "done"}
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            yield {"type": "done"}
