from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks
from ultrafast_memory.rag.query_service import clear_rag_query_cache, query_rag


def test_index_service_skips_unchanged_chunks(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default", "embedding_dimension": 32})
    first = index_pending_chunks(index["index_id"])
    second = index_pending_chunks(index["index_id"])
    assert first["indexed_count"] > 0
    assert second["indexed_count"] == 0
    assert second["skipped_count"] == first["active_chunk_count"]


def test_query_cache_is_revision_and_database_scoped(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default", "embedding_dimension": 32})
    index_pending_chunks(index["index_id"])
    clear_rag_query_cache()

    first = query_rag({"query": "TGV taper crack", "top_k": 4})
    second = query_rag({"query": "TGV taper crack", "top_k": 4})

    assert first["retrieval_metadata"]["cache_hit"] is False
    assert second["retrieval_metadata"]["cache_hit"] is True
    assert [item["chunk_id"] for item in first["hits"]] == [item["chunk_id"] for item in second["hits"]]
    assert second["retrieval_metadata"]["waterfall_ms"]["retrieval"] < first["retrieval_metadata"]["waterfall_ms"]["retrieval"]


def test_real_embedding_failure_degrades_to_searchable_lexical_without_mock_fallback(
    isolated_root, mixed_literature_root, monkeypatch,
):
    init_database()
    ingest_literature(str(mixed_literature_root))
    monkeypatch.delenv("ULTRAFAST_EMBEDDING_API_KEY", raising=False)
    index = create_index({
        "index_name": "literature_default",
        "embedding_provider": "openai_compatible",
        "embedding_model": "test-embedding",
        "embedding_dimension": 32,
        "embedding": {"base_url": "https://embedding.invalid/v1"},
    })

    indexed = index_pending_chunks(index["index_id"])
    clear_rag_query_cache()
    result = query_rag({"query": "TGV taper crack", "top_k": 4})

    assert indexed["status"] == "degraded"
    assert indexed["indexed_count"] == 0
    assert indexed["lexical_indexed_count"] > 0
    assert indexed["embedding_provider"] == "openai_compatible"
    assert result["hits"]
    assert result["retrieval_metadata"]["degraded"] is True
    assert result["retrieval_metadata"]["fallback"] == "sqlite_lexical"

    incremental = index_pending_chunks(index["index_id"])
    assert incremental["status"] == "degraded"
    assert incremental["indexed_count"] == 0
    assert incremental["lexical_indexed_count"] == 0
    assert incremental["skipped_count"] == indexed["active_chunk_count"]
    assert incremental["lexical_only_entry_count"] == indexed["active_chunk_count"]


def test_embedding_dimension_change_creates_a_distinct_auditable_index(isolated_root):
    first = create_index({
        "index_name": "dimensioned",
        "embedding_provider": "mock",
        "embedding_model": "test-model",
        "embedding_dimension": 32,
    })
    second = create_index({
        "index_name": "dimensioned",
        "embedding_provider": "mock",
        "embedding_model": "test-model",
        "embedding_dimension": 64,
    })

    assert first["index_id"] != second["index_id"]
    assert first["embedding_dimension"] == 32
    assert second["embedding_dimension"] == 64
