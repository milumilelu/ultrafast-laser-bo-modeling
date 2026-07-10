from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.citation_builder import build_citations
from ultrafast_memory.rag.embedding import DeterministicMockEmbeddingProvider
from ultrafast_memory.rag.evidence_pack import build_evidence_pack
from ultrafast_memory.rag.hybrid_retriever import HybridRetriever
from ultrafast_memory.rag.index_service import get_index_by_name
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.schemas import RagQueryRequest
from ultrafast_memory.rag.vector_store import SQLiteVectorStore


def query_rag(request: RagQueryRequest | dict[str, Any]) -> dict[str, Any]:
    req = request if isinstance(request, RagQueryRequest) else RagQueryRequest.model_validate(request)
    index = get_index_by_name(req.index_name)
    if not index:
        pack = build_evidence_pack(req.query, req.filters, [])
        pack["warnings"].append(f"RAG index not found: {req.index_name}")
        pack["citations"] = []
        return pack
    provider = DeterministicMockEmbeddingProvider(int(index.get("embedding_dimension") or 64))
    retriever = HybridRetriever(provider, SQLiteVectorStore(index["index_id"]), SQLiteLexicalIndex())
    config = json.loads(index.get("config_json") or "{}")
    retrieval = config.get("retrieval") or {}
    results = retriever.retrieve(
        normalize_query(req.query),
        req.filters,
        req.purpose,
        lexical_top_k=int(retrieval.get("lexical_top_k", 20)),
        vector_top_k=int(retrieval.get("vector_top_k", 20)),
        fusion_top_k=int(retrieval.get("fusion_top_k", 15)),
        rerank_top_k=min(req.top_k, int(retrieval.get("rerank_top_k", req.top_k))),
        max_chunks_per_paper=int(retrieval.get("max_chunks_per_paper", 3)),
    )
    pack = build_evidence_pack(req.query, req.filters, results["hits"])
    pack["citations"] = build_citations(pack)
    _record_trace(req, results, pack)
    return pack


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _record_trace(req: RagQueryRequest, results: dict[str, Any], pack: dict[str, Any]) -> None:
    query_id = stable_id("rag_query", req.session_id, req.query, utc_now_iso(), uuid.uuid4().hex)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO rag_query_trace VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                query_id, req.session_id, req.query, normalize_query(req.query), json.dumps(req.filters, ensure_ascii=False),
                json.dumps(_compact(results["lexical_hits"]), ensure_ascii=False),
                json.dumps(_compact(results["vector_hits"]), ensure_ascii=False),
                json.dumps(_compact(results["hits"]), ensure_ascii=False),
                json.dumps(pack, ensure_ascii=False), utc_now_iso(),
            ),
        )
        conn.commit()


def _compact(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: hit.get(key) for key in ("chunk_id", "paper_id", "score")} for hit in hits]
