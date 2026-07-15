from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from typing import Any


class BaseEmbeddingProvider:
    provider = "base"
    model = "base"
    dimension = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class DeterministicMockEmbeddingProvider(BaseEmbeddingProvider):
    provider = "mock"
    model = "deterministic-mock-v1"

    def __init__(self, dimension: int = 64):
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    provider = "sentence_transformers"

    def __init__(
        self,
        model: str,
        *,
        dimension: int | None = None,
        device: str | None = None,
        batch_size: int = 8,
        local_files_only: bool = False,
    ):
        self.model = model
        self.batch_size = max(1, int(batch_size))
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for the configured RAG embedding provider"
            ) from exc
        self._client = SentenceTransformer(
            model,
            device=device,
            local_files_only=bool(local_files_only),
        )
        actual = self._client.get_sentence_embedding_dimension()
        self.dimension = int(actual or dimension or 0)
        if dimension and self.dimension != dimension:
            raise ValueError(
                f"embedding dimension mismatch: configured={dimension}, model={self.dimension}"
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._client.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [[float(value) for value in row] for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAICompatibleEmbeddingProvider(BaseEmbeddingProvider):
    provider = "openai_compatible"

    def __init__(
        self,
        model: str,
        *,
        dimension: int,
        base_url: str,
        api_key: str,
        timeout_s: float = 60.0,
        batch_size: int = 64,
    ):
        self.model = model
        self.dimension = int(dimension)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.batch_size = max(1, int(batch_size))
        if not self.base_url or not self.api_key or self.dimension <= 0:
            raise ValueError("OpenAI-compatible embedding requires base_url, api_key, and dimension")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        output: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            output.extend(self._embed_batch(texts[start:start + self.batch_size]))
        return output

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        endpoint = self.base_url if self.base_url.endswith("/embeddings") else f"{self.base_url}/embeddings"
        body = json.dumps({"model": self.model, "input": texts}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("embedding response is missing data")
        ordered = sorted(rows, key=lambda item: int(item.get("index") or 0))
        vectors = [item.get("embedding") for item in ordered]
        if len(vectors) != len(texts) or any(not isinstance(row, list) for row in vectors):
            raise RuntimeError("embedding response count or shape mismatch")
        batch = [[float(value) for value in row] for row in vectors]
        if any(len(row) != self.dimension for row in batch):
            raise RuntimeError("embedding response dimension mismatch")
        return batch

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedding_provider(
    provider: str,
    model: str,
    dimension: int,
    config: dict[str, Any] | None = None,
) -> BaseEmbeddingProvider:
    options = config or {}
    normalized = provider.strip().lower()
    if normalized == "mock":
        return DeterministicMockEmbeddingProvider(dimension)
    if normalized in {"sentence_transformers", "sentence-transformers", "local"}:
        return SentenceTransformerEmbeddingProvider(
            model,
            dimension=dimension,
            device=options.get("device"),
            batch_size=int(options.get("batch_size") or 8),
            local_files_only=bool(options.get("local_files_only", False)),
        )
    if normalized in {"openai_compatible", "openai-compatible", "openai"}:
        api_key_env = str(options.get("api_key_env") or "ULTRAFAST_EMBEDDING_API_KEY")
        base_url = str(
            options.get("base_url")
            or os.environ.get("ULTRAFAST_EMBEDDING_BASE_URL")
            or ""
        )
        api_key = str(os.environ.get(api_key_env) or "")
        return OpenAICompatibleEmbeddingProvider(
            model,
            dimension=dimension,
            base_url=base_url,
            api_key=api_key,
            timeout_s=float(options.get("timeout_s") or 60),
            batch_size=int(options.get("batch_size") or 64),
        )
    raise ValueError(f"unsupported embedding provider: {provider}")


LocalEmbeddingProvider = SentenceTransformerEmbeddingProvider
