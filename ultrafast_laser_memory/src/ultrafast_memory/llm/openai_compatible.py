from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from ultrafast_memory.llm.base import BaseLLMClient


class LLMProviderError(RuntimeError):
    """Provider failure whose message is safe to expose without credentials."""

    def __init__(self, message: str, *, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, config: dict[str, Any]):
        self.provider = config.get("provider") or "openai"
        self.model = config.get("model") or ""
        self.api_base = (config.get("api_base") or "").rstrip("/")
        self.api_key_env = config.get("api_key_env") or ""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> dict:
        api_key = self._require_configuration()
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
            raise _provider_http_error(exc.code, detail) from exc
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
        try:
            api_key = self._require_configuration()
        except LLMProviderError as exc:
            yield _error_event(exc)
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
            yield _error_event(_provider_http_error(exc.code, detail))
            yield {"type": "done"}
        except Exception as exc:
            yield _error_event(LLMProviderError(f"语言模型连接失败（{type(exc).__name__}）。"))
            yield {"type": "done"}

    def test_connection(self, **kwargs: Any) -> dict[str, Any]:
        """Validate credentials/model discovery without consuming chat tokens."""
        api_key = self._require_configuration()
        request = urllib.request.Request(
            f"{self.api_base}/models",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=kwargs.get("timeout", 20)) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise _provider_http_error(exc.code, detail) from exc
        except Exception as exc:
            raise LLMProviderError(f"语言模型连接失败（{type(exc).__name__}）。") from exc
        model_ids = [item.get("id") for item in raw.get("data", []) if isinstance(item, dict)]
        if self.model and self.model not in model_ids:
            raise LLMProviderError(
                f"配置模型 {self.model} 不在供应商返回的可用模型列表中。",
                error_code="model_not_available",
            )
        return {"ok": True, "provider": self.provider, "model": self.model}

    def _require_configuration(self) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise LLMProviderError("未找到语言模型 API Key。", error_code="missing_api_key")
        if not self.api_base:
            raise LLMProviderError("未配置语言模型 API Base URL。", error_code="missing_api_base")
        return api_key


def _provider_http_error(status_code: int, detail: str) -> LLMProviderError:
    error_code = None
    try:
        payload = json.loads(detail)
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            error_code = error.get("code")
    except (json.JSONDecodeError, TypeError):
        pass
    messages = {
        401: "语言模型认证失败：API Key 无效或已撤销，请重新配置。",
        402: "语言模型账户余额不足，请充值后重试。",
        403: "语言模型请求被拒绝，请检查账户或模型权限。",
        404: "语言模型接口或模型不存在，请检查 API Base URL 和模型名。",
        429: "语言模型请求过于频繁或额度受限，请稍后重试。",
        503: "所选语言模型当前容量已满，请稍后重试或切换可用模型。",
    }
    capacity_markers = ("at capacity", "overloaded", "capacity", "model is busy")
    if any(marker in detail.lower() for marker in capacity_markers):
        message = "所选语言模型当前容量已满，请稍后重试或切换可用模型。"
        error_code = error_code or "model_capacity_exceeded"
    else:
        message = messages.get(status_code, f"语言模型供应商返回 HTTP {status_code}。")
    return LLMProviderError(message, status_code=status_code, error_code=error_code)


def _error_event(exc: LLMProviderError) -> dict[str, Any]:
    return {
        "type": "error",
        "message": str(exc),
        "safe_to_display": True,
        "status_code": exc.status_code,
        "error_code": exc.error_code,
    }
