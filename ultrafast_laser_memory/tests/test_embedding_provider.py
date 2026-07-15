from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np

from ultrafast_memory.rag.embedding import (
    OpenAICompatibleEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_openai_compatible_embedding_provider_calls_embeddings_endpoint(monkeypatch) -> None:
    observed = {}

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["authorization"] = request.headers["Authorization"]
        observed["body"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return _Response({
            "data": [
                {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                {"index": 1, "embedding": [0.0, 1.0, 0.0]},
            ]
        })

    monkeypatch.setattr("ultrafast_memory.rag.embedding.urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleEmbeddingProvider(
        "embedding-model",
        dimension=3,
        base_url="https://embedding.example/v1",
        api_key="secret",
        timeout_s=12,
    )

    vectors = provider.embed_documents(["出口崩边", "exit-side chipping"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert observed["url"] == "https://embedding.example/v1/embeddings"
    assert observed["authorization"] == "Bearer secret"
    assert observed["body"] == {
        "model": "embedding-model",
        "input": ["出口崩边", "exit-side chipping"],
    }
    assert observed["timeout"] == 12


def test_sentence_transformer_provider_uses_model_dimension_and_normalized_encode(
    monkeypatch,
) -> None:
    observed = {}

    class FakeSentenceTransformer:
        def __init__(self, model, device=None, local_files_only=False):
            observed.update({
                "model": model,
                "device": device,
                "local_files_only": local_files_only,
            })

        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, texts, **kwargs):
            observed.update({"texts": texts, **kwargs})
            return np.asarray([[1.0, 0.0, 0.0] for _ in texts])

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    provider = SentenceTransformerEmbeddingProvider(
        "local-model", dimension=3, device="cpu"
    )

    assert provider.embed_query("出口崩边") == [1.0, 0.0, 0.0]
    assert observed == {
        "model": "local-model",
        "device": "cpu",
        "local_files_only": False,
        "texts": ["出口崩边"],
        "batch_size": 8,
        "normalize_embeddings": True,
        "convert_to_numpy": True,
    }
