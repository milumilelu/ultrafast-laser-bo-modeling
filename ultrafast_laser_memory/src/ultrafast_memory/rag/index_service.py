from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.embedding import DeterministicMockEmbeddingProvider
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.vector_store import SQLiteVectorStore


def create_index(config: dict[str, Any]) -> dict[str, Any]:
    init_database()
    name = config.get("index_name") or config.get("name") or "literature_default"
    provider = config.get("embedding_provider") or "mock"
    model = config.get("embedding_model") or "deterministic-mock-v1"
    dimension = int(config.get("embedding_dimension") or 64)
    if provider != "mock":
        raise ValueError("offline MVP currently enables only the deterministic mock embedding provider")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM rag_index WHERE index_name=? AND embedding_provider=? AND embedding_model=? ORDER BY created_at DESC LIMIT 1",
            (name, provider, model),
        ).fetchone()
        if existing:
            return dict(existing)
        now = utc_now_iso()
        record = {
            "index_id": stable_id("rag_index", name, provider, model, dimension),
            "index_name": name,
            "index_type": "hybrid",
            "embedding_provider": provider,
            "embedding_model": model,
            "embedding_dimension": dimension,
            "distance_metric": "cosine",
            "config_json": json.dumps(config, ensure_ascii=False),
            "status": "created",
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            "INSERT INTO rag_index VALUES (:index_id,:index_name,:index_type,:embedding_provider,:embedding_model,:embedding_dimension,:distance_metric,:config_json,:status,:created_at,:updated_at)",
            record,
        )
        conn.commit()
    SQLiteLexicalIndex()
    return record


def index_pending_chunks(index_id: str, force: bool = False) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        index = conn.execute("SELECT * FROM rag_index WHERE index_id=?", (index_id,)).fetchone()
        if not index:
            raise ValueError(f"index not found: {index_id}")
        rows = conn.execute(
            """
            SELECT c.*,p.canonical_title,p.material,p.material_grade,p.process_type,p.component_type
            FROM literature_chunk c JOIN literature_paper p ON p.paper_id=c.paper_id
            WHERE c.active=1
            """
        ).fetchall()
        existing = {
            row["chunk_id"]: row["content_hash"]
            for row in conn.execute("SELECT chunk_id,content_hash FROM rag_index_entry WHERE index_id=? AND status='indexed'", (index_id,)).fetchall()
        }
    pending = [dict(row) for row in rows if force or existing.get(row["chunk_id"]) != row["content_hash"]]
    skipped = len(rows) - len(pending)
    provider = DeterministicMockEmbeddingProvider(int(index["embedding_dimension"] or 64))
    vector_entries = []
    lexical_entries = []
    vectors = provider.embed_documents([row["content"] for row in pending])
    for row, vector in zip(pending, vectors):
        vector_entries.append({"chunk_id": row["chunk_id"], "content_hash": row["content_hash"], "vector": vector})
        lexical_entries.append(
            {
                "chunk_id": row["chunk_id"], "content": row["content"], "title": row.get("canonical_title") or "",
                "material": row.get("material") or "", "material_grade": row.get("material_grade") or "",
                "process_type": row.get("process_type") or "", "component_type": row.get("component_type") or "",
                "section_title": row.get("section_title") or "",
            }
        )
    if vector_entries:
        SQLiteVectorStore(index_id).upsert(vector_entries)
        SQLiteLexicalIndex().upsert(lexical_entries)
    with get_connection() as conn:
        if pending:
            conn.executemany(
                "UPDATE rag_index_entry SET status='indexed',lexical_ref=? WHERE index_id=? AND chunk_id=?",
                [(row["chunk_id"], index_id, row["chunk_id"]) for row in pending],
            )
        conn.execute("UPDATE rag_index SET status='ready',updated_at=? WHERE index_id=?", (utc_now_iso(), index_id))
        inactive = [row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM literature_chunk WHERE active=0").fetchall()]
        conn.commit()
    if inactive:
        SQLiteVectorStore(index_id).delete(inactive)
        SQLiteLexicalIndex().delete(inactive)
    return {"index_id": index_id, "indexed_count": len(pending), "skipped_count": skipped, "active_chunk_count": len(rows), "status": "ready"}


def rebuild_index(index_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        conn.execute("DELETE FROM rag_index_entry WHERE index_id=?", (index_id,))
        conn.commit()
    return index_pending_chunks(index_id, force=True)


def get_index_status(index_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM rag_index WHERE index_id=?", (index_id,)).fetchone()
        if not row:
            raise ValueError(f"index not found: {index_id}")
        result = dict(row)
        result["entry_count"] = conn.execute("SELECT count(*) AS count FROM rag_index_entry WHERE index_id=? AND status='indexed'", (index_id,)).fetchone()["count"]
        return result


def get_index_by_name(name: str) -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM rag_index WHERE index_name=? ORDER BY created_at DESC LIMIT 1", (name,)).fetchone()
    return dict(row) if row else None
