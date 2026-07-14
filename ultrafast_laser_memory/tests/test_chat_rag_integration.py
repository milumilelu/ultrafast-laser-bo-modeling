from ultrafast_agent.runtime import ToolExecutor
from ultrafast_memory.agent_runtime.tool_registry import build_main_agent_tool_registry
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.literature.service import ingest_literature
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks


def test_main_agent_rag_tool_uses_only_real_chunks(isolated_root, mixed_literature_root):
    init_database()
    ingest_literature(str(mixed_literature_root))
    index = create_index({"index_name": "literature_default"})
    index_pending_chunks(index["index_id"])
    execution = ToolExecutor(build_main_agent_tool_registry()).execute(
        "search_knowledge",
        {"query": "TGV 玻璃通孔锥度和裂纹", "top_k": 8},
        {"task_spec": {"material": "glass_wafer", "process_type": "hole_drilling"}},
    )
    assert execution.status == "succeeded"
    assert execution.output["hits"]
    assert all(hit.get("chunk_id") for hit in execution.output["hits"])
