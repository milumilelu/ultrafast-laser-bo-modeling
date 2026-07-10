from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.literature.service import ingest_literature


def test_ingestion_is_idempotent_and_deduplicates_doi(isolated_root, mixed_literature_root):
    init_database()
    first = ingest_literature(str(mixed_literature_root))
    second = ingest_literature(str(mixed_literature_root))
    assert first["status"] == "completed"
    with get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM literature_paper").fetchone()[0] == 1
        chunk_count = conn.execute("SELECT count(*) FROM literature_chunk").fetchone()[0]
    assert chunk_count > 0
    assert second["chunk_count"] == 0
