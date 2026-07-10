from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks


def test_index_service_skips_unchanged_chunks(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default", "embedding_dimension": 32})
    first = index_pending_chunks(index["index_id"])
    second = index_pending_chunks(index["index_id"])
    assert first["indexed_count"] > 0
    assert second["indexed_count"] == 0
    assert second["skipped_count"] == first["active_chunk_count"]
