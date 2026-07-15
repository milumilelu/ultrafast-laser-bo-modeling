from __future__ import annotations

import json
import re
import uuid
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import perf_counter
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.config import get_database_path, load_config
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.citation_builder import build_citations
from ultrafast_memory.rag.embedding import build_embedding_provider
from ultrafast_memory.rag.evidence_pack import build_evidence_pack
from ultrafast_memory.rag.hybrid_retriever import HybridRetriever
from ultrafast_memory.rag.index_service import get_index_by_name
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.metadata_filter import apply_metadata_filters
from ultrafast_memory.rag.reranker import rerank_hits
from ultrafast_memory.rag.schemas import RagQueryRequest
from ultrafast_memory.rag.vector_store import SQLiteVectorStore


_QUERY_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_CACHE_LOCK = Lock()


def query_rag(request: RagQueryRequest | dict[str, Any]) -> dict[str, Any]:
    total_started = perf_counter()
    req = request if isinstance(request, RagQueryRequest) else RagQueryRequest.model_validate(request)
    stage = perf_counter()
    try:
        index = get_index_by_name(req.index_name)
    except Exception as exc:
        return _degraded_pack(req, "index_lookup", exc, total_started)
    index_lookup_ms = (perf_counter() - stage) * 1000
    if not index:
        pack = build_evidence_pack(req.query, req.filters, [], purpose=req.purpose)
        pack["warnings"].append(f"RAG index not found: {req.index_name}")
        pack["citations"] = []
        return pack
    config = json.loads(index.get("config_json") or "{}")
    retrieval = config.get("retrieval") or {}
    cache_key = _cache_key(req, index, retrieval)
    stage = perf_counter()
    results = _cache_get(cache_key)
    cache_hit = results is not None
    retrieval_failure: Exception | None = None
    if results is None:
        if index.get("status") != "ready":
            retrieval_failure = RuntimeError(
                f"vector index is not ready: {index.get('status') or 'unknown'}"
            )
            try:
                results = _lexical_fallback(req, retrieval, stage)
            except Exception as exc:
                return _degraded_pack(
                    req,
                    "retrieval",
                    exc,
                    total_started,
                    index=index,
                    index_lookup_ms=index_lookup_ms,
                )
        else:
            try:
                embedding_options = config.get("embedding") or {}
                provider = build_embedding_provider(
                    str(index.get("embedding_provider") or embedding_options.get("provider") or "mock"),
                    str(index.get("embedding_model") or embedding_options.get("model") or "deterministic-mock-v1"),
                    int(index.get("embedding_dimension") or embedding_options.get("dimension") or 64),
                    embedding_options,
                )
                retriever = HybridRetriever(
                    provider, SQLiteVectorStore(index["index_id"]), SQLiteLexicalIndex()
                )
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
                _cache_put(cache_key, results)
            except Exception as exc:
                retrieval_failure = exc
                try:
                    results = _lexical_fallback(req, retrieval, stage)
                except Exception:
                    return _degraded_pack(
                        req,
                        "retrieval",
                        exc,
                        total_started,
                        index=index,
                        index_lookup_ms=index_lookup_ms,
                    )
    retrieval_ms = (perf_counter() - stage) * 1000
    stage = perf_counter()
    pack = build_evidence_pack(req.query, req.filters, results["hits"], purpose=req.purpose)
    pack["citations"] = build_citations(pack)
    evidence_pack_ms = (perf_counter() - stage) * 1000
    pack["retrieval_metadata"] = {
        "cache_hit": cache_hit,
        "index_id": index["index_id"],
        "index_revision": index.get("updated_at"),
        "waterfall_ms": {
            "index_lookup": round(index_lookup_ms, 3),
            "retrieval": round(retrieval_ms, 3),
            "evidence_pack": round(evidence_pack_ms, 3),
            "total_before_trace": round((perf_counter() - total_started) * 1000, 3),
        },
        "source_retrieval_waterfall_ms": results.get("waterfall_ms") or {},
    }
    if retrieval_failure is not None:
        pack["warnings"].append("Hybrid RAG unavailable; lexical fallback used")
        pack["retrieval_metadata"].update(
            {
                "degraded": True,
                "failure_stage": "hybrid_retrieval",
                "error_type": type(retrieval_failure).__name__,
                "fallback": "sqlite_lexical",
            }
        )
    stage = perf_counter()
    try:
        _record_trace(req, results, pack)
    except Exception as exc:
        pack["warnings"].append("RAG trace persistence unavailable; response was not discarded")
        pack["retrieval_metadata"]["trace_error_type"] = type(exc).__name__
    pack["retrieval_metadata"]["waterfall_ms"]["trace_write"] = round(
        (perf_counter() - stage) * 1000, 3
    )
    pack["retrieval_metadata"]["waterfall_ms"]["total"] = round(
        (perf_counter() - total_started) * 1000, 3
    )
    return pack


def _degraded_pack(
    req: RagQueryRequest,
    stage: str,
    error: Exception,
    total_started: float,
    *,
    index: dict[str, Any] | None = None,
    index_lookup_ms: float | None = None,
) -> dict[str, Any]:
    pack = build_evidence_pack(req.query, req.filters, [], purpose=req.purpose)
    pack["warnings"].append(f"RAG {stage} unavailable; no evidence returned")
    pack["citations"] = []
    pack["retrieval_metadata"] = {
        "degraded": True,
        "failure_stage": stage,
        "error_type": type(error).__name__,
        "cache_hit": False,
        "index_id": index.get("index_id") if index else None,
        "index_revision": index.get("updated_at") if index else None,
        "waterfall_ms": {
            "index_lookup": round(index_lookup_ms or 0.0, 3),
            "total": round((perf_counter() - total_started) * 1000, 3),
        },
        "source_retrieval_waterfall_ms": {},
    }
    return pack


def _lexical_fallback(
    req: RagQueryRequest,
    retrieval: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    lexical_limit = int(retrieval.get("lexical_top_k", 20))
    lexical = apply_metadata_filters(
        SQLiteLexicalIndex().search(
            normalize_query(req.query),
            lexical_limit * 5 if req.filters else lexical_limit,
        ),
        req.filters,
    )
    lexical = rerank_hits(
        lexical, req.filters, req.purpose, min(req.top_k, lexical_limit)
    )
    return {
        "lexical_hits": lexical,
        "vector_hits": [],
        "hits": lexical,
        "waterfall_ms": {
            "fallback_lexical": round((perf_counter() - started) * 1000, 3)
        },
    }


def clear_rag_query_cache() -> None:
    with _CACHE_LOCK:
        _QUERY_CACHE.clear()


def _cache_key(req: RagQueryRequest, index: dict[str, Any], retrieval: dict[str, Any]) -> str:
    return json.dumps(
        {
            "database": str(get_database_path()),
            "index_id": index["index_id"],
            "index_revision": index.get("updated_at"),
            "query": normalize_query(req.query),
            "filters": req.filters,
            "purpose": req.purpose,
            "top_k": req.top_k,
            "retrieval": retrieval,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cache_get(key: str) -> dict[str, Any] | None:
    with _CACHE_LOCK:
        value = _QUERY_CACHE.get(key)
        if value is None:
            return None
        _QUERY_CACHE.move_to_end(key)
        return deepcopy(value)


def _cache_put(key: str, value: dict[str, Any]) -> None:
    maximum = int(load_config().get("performance", {}).get("rag_cache_size", 128))
    with _CACHE_LOCK:
        _QUERY_CACHE[key] = deepcopy(value)
        _QUERY_CACHE.move_to_end(key)
        while len(_QUERY_CACHE) > max(1, maximum):
            _QUERY_CACHE.popitem(last=False)


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
