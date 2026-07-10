from __future__ import annotations

import hashlib
import math
import re


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

    def __init__(self, model: str):
        self.model = model
        raise NotImplementedError("SentenceTransformer provider is an adapter placeholder in the MVP")


class OpenAICompatibleEmbeddingProvider(BaseEmbeddingProvider):
    provider = "openai_compatible"

    def __init__(self, model: str):
        self.model = model
        raise NotImplementedError("OpenAI-compatible embedding provider is not enabled in offline MVP")


LocalEmbeddingProvider = SentenceTransformerEmbeddingProvider
