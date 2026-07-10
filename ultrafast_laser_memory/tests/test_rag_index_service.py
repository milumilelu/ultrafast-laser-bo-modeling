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
