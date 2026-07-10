from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks


def test_chat_uses_only_real_rag_chunks(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default"})
    index_pending_chunks(index["index_id"])
    response = handle_chat(ChatRequest(message="请查找 TGV 玻璃通孔锥度和裂纹相关文献", use_skills=True))
    assert response.selected_skill == "rag_literature_retrieval"
    assert response.rag_evidence is not None
    assert response.citations
    chunk_ids = {hit["chunk_id"] for hit in response.rag_evidence["hits"]}
    assert {item["chunk_id"] for item in response.citations} <= chunk_ids
    assert "确定性工艺参数" in response.assistant_message or response.rag_evidence["evidence_status"] == "sufficient"
