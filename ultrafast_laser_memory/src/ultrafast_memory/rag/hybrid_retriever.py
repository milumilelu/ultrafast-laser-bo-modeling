from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from typing import Any

from ultrafast_memory.rag.embedding import BaseEmbeddingProvider
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.metadata_filter import apply_metadata_filters
from ultrafast_memory.rag.reranker import rerank_hits
from ultrafast_memory.rag.vector_store import BaseVectorStore


def reciprocal_rank_fusion(result_lists: list[list[dict[str, Any]]], top_k: int = 15, k: int = 60) -> list[dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    rows: dict[str, dict[str, Any]] = {}
    for result_list in result_lists:
        for rank, hit in enumerate(result_list, 1):
            chunk_id = hit["chunk_id"]
            scores[chunk_id] += 1.0 / (k + rank)
            rows.setdefault(chunk_id, hit)
    fused = [{**rows[chunk_id], "score": score} for chunk_id, score in scores.items()]
    return sorted(fused, key=lambda row: row["score"], reverse=True)[:top_k]


class HybridRetriever:
    def __init__(
        self,
        embedding: BaseEmbeddingProvider,
        vector_store: BaseVectorStore,
        lexical_index: SQLiteLexicalIndex,
    ):
        self.embedding = embedding
        self.vector_store = vector_store
        self.lexical_index = lexical_index

    def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        purpose: str = "literature_background",
        lexical_top_k: int = 20,
        vector_top_k: int = 20,
        fusion_top_k: int = 15,
        rerank_top_k: int = 8,
        max_chunks_per_paper: int = 3,
    ) -> dict[str, Any]:
        started = perf_counter()
        lexical_pool = lexical_top_k * 5 if filters else lexical_top_k
        stage = perf_counter()
        lexical = apply_metadata_filters(self.lexical_index.search(query, lexical_pool), filters)[:lexical_top_k]
        lexical_ms = (perf_counter() - stage) * 1000
        stage = perf_counter()
        vector = apply_metadata_filters(self.vector_store.query(self.embedding.embed_query(query), vector_top_k, filters), filters)
        vector_ms = (perf_counter() - stage) * 1000
        stage = perf_counter()
        fused = reciprocal_rank_fusion([lexical, vector], fusion_top_k)
        fusion_ms = (perf_counter() - stage) * 1000
        stage = perf_counter()
        reranked = rerank_hits(fused, filters, purpose, rerank_top_k * 2)
        limited = []
        paper_counts: dict[str, int] = defaultdict(int)
        for hit in reranked:
            if paper_counts[hit["paper_id"]] >= max_chunks_per_paper:
                continue
            limited.append(hit)
            paper_counts[hit["paper_id"]] += 1
            if len(limited) >= rerank_top_k:
                break
        rerank_ms = (perf_counter() - stage) * 1000
        return {
            "lexical_hits": lexical,
            "vector_hits": vector,
            "hits": limited,
            "waterfall_ms": {
                "lexical": round(lexical_ms, 3),
                "vector": round(vector_ms, 3),
                "fusion": round(fusion_ms, 3),
                "rerank_and_limit": round(rerank_ms, 3),
                "total": round((perf_counter() - started) * 1000, 3),
            },
        }
