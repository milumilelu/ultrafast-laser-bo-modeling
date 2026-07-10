from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks
from ultrafast_memory.rag.query_service import query_rag


def test_hybrid_retrieval_uses_lexical_and_vector(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default"})
    index_pending_chunks(index["index_id"])
    pack = query_rag({
        "query": "TGV taper microcrack glass wafer drilling",
        "filters": {"scenario_id": "scenario_05_tgv_drilling", "material": "glass_wafer"},
    })
    assert pack["hits"]
    assert all(hit["paper_id"] == "paper_tgv_test" for hit in pack["hits"])
    assert pack["citations"][0]["chunk_id"] == pack["hits"][0]["chunk_id"]
