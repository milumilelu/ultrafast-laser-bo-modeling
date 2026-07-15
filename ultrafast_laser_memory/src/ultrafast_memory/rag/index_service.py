from __future__ import annotations

import json
import uuid
from typing import Any

from ultrafast_memory.core.config import load_config
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.canonical_document import materialize_rag_document
from ultrafast_memory.rag.embedding import build_embedding_provider
from ultrafast_memory.rag.lexical_index import SQLiteLexicalIndex
from ultrafast_memory.rag.vector_store import SQLiteVectorStore


def create_index(config: dict[str, Any]) -> dict[str, Any]:
    init_database()
    rag_config = load_config().get("rag", {})
    embedding_config = {
        **(rag_config.get("embedding") or {}),
        **(config.get("embedding") or {}),
    }
    name = config.get("index_name") or config.get("name") or rag_config.get(
        "default_index_name", "literature_default"
    )
    provider = config.get("embedding_provider") or embedding_config.get("provider") or "mock"
    model = config.get("embedding_model") or embedding_config.get("model") or "deterministic-mock-v1"
    dimension = int(
        config.get("embedding_dimension") or embedding_config.get("dimension") or 64
    )
    if provider not in {
        "mock", "sentence_transformers", "sentence-transformers", "local",
        "openai_compatible", "openai-compatible", "openai",
    }:
        raise ValueError(f"unsupported embedding provider: {provider}")
    stored_config = {
        **rag_config,
        **config,
        "index_name": name,
        "embedding": {
            **embedding_config,
            "provider": provider,
            "model": model,
            "dimension": dimension,
        },
    }
    stored_config["embedding"].pop("api_key", None)
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT * FROM rag_index
            WHERE index_name=? AND embedding_provider=? AND embedding_model=?
              AND embedding_dimension=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (name, provider, model, dimension),
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
            "config_json": json.dumps(stored_config, ensure_ascii=False),
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
            row["chunk_id"]: dict(row)
            for row in conn.execute(
                "SELECT chunk_id,content_hash,status FROM rag_index_entry WHERE index_id=?",
                (index_id,),
            ).fetchall()
        }
    pending = [
        dict(row)
        for row in rows
        if force
        or row["chunk_id"] not in existing
        or existing[row["chunk_id"]]["content_hash"] != row["content_hash"]
    ]
    skipped = len(rows) - len(pending)
    lexical_entries = [
        {
            "chunk_id": row["chunk_id"], "content": row["content"],
            "title": row.get("canonical_title") or "",
            "material": row.get("material") or "",
            "material_grade": row.get("material_grade") or "",
            "process_type": row.get("process_type") or "",
            "component_type": row.get("component_type") or "",
            "section_title": row.get("section_title") or "",
        }
        for row in pending
    ]
    lexical_index = SQLiteLexicalIndex()
    if lexical_entries:
        lexical_index.upsert(lexical_entries)
    embedding_error: Exception | None = None
    vector_entries: list[dict[str, Any]] = []
    if pending:
        try:
            provider = _embedding_for_index(dict(index))
            vectors = provider.embed_documents([row["content"] for row in pending])
            if len(vectors) != len(pending):
                raise RuntimeError("embedding provider returned an unexpected vector count")
            vector_entries = [
                {"chunk_id": row["chunk_id"], "content_hash": row["content_hash"], "vector": vector}
                for row, vector in zip(pending, vectors)
            ]
            SQLiteVectorStore(index_id).upsert(vector_entries)
        except Exception as exc:  # noqa: BLE001 - lexical indexing remains usable
            embedding_error = exc
    with get_connection() as conn:
        if vector_entries:
            conn.executemany(
                "UPDATE rag_index_entry SET status='indexed',lexical_ref=? WHERE index_id=? AND chunk_id=?",
                [(row["chunk_id"], index_id, row["chunk_id"]) for row in pending],
            )
        elif pending:
            now = utc_now_iso()
            conn.executemany(
                """
                INSERT INTO rag_index_entry (
                  entry_id,index_id,chunk_id,vector_ref,lexical_ref,content_hash,indexed_at,status,error_message
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(index_id,chunk_id) DO UPDATE SET
                  lexical_ref=excluded.lexical_ref,content_hash=excluded.content_hash,
                  indexed_at=excluded.indexed_at,status='lexical_indexed',
                  error_message=excluded.error_message
                """,
                [
                    (
                        stable_id("rag_entry", index_id, row["chunk_id"]), index_id,
                        row["chunk_id"], None, row["chunk_id"], row["content_hash"], now,
                        "lexical_indexed", type(embedding_error).__name__ if embedding_error else None,
                    )
                    for row in pending
                ],
            )
        lexical_only = conn.execute(
            "SELECT COUNT(*) FROM rag_index_entry WHERE index_id=? AND status='lexical_indexed'",
            (index_id,),
        ).fetchone()[0]
        status = "degraded" if embedding_error or lexical_only else "ready"
        conn.execute(
            "UPDATE rag_index SET status=?,updated_at=? WHERE index_id=?",
            (status, utc_now_iso(), index_id),
        )
        inactive = [row["chunk_id"] for row in conn.execute("SELECT chunk_id FROM literature_chunk WHERE active=0").fetchall()]
        conn.commit()
    if inactive:
        SQLiteVectorStore(index_id).delete(inactive)
        lexical_index.delete(inactive)
    return {
        "index_id": index_id,
        "indexed_count": len(vector_entries),
        "lexical_indexed_count": len(pending),
        "skipped_count": skipped,
        "active_chunk_count": len(rows),
        "status": status,
        "embedding_provider": index["embedding_provider"],
        "embedding_error_type": type(embedding_error).__name__ if embedding_error else None,
        "lexical_only_entry_count": int(lexical_only),
    }


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
        counts = {
            item["status"]: int(item["count"])
            for item in conn.execute(
                """
                SELECT status,COUNT(*) AS count FROM rag_index_entry
                WHERE index_id=? GROUP BY status
                """,
                (index_id,),
            ).fetchall()
        }
        result["entry_count"] = counts.get("indexed", 0)
        result["vector_entry_count"] = counts.get("indexed", 0)
        result["lexical_only_entry_count"] = counts.get("lexical_indexed", 0)
        result["active_chunk_count"] = int(
            conn.execute(
                "SELECT COUNT(*) FROM literature_chunk WHERE active=1"
            ).fetchone()[0]
        )
        return result


def get_index_by_name(name: str) -> dict[str, Any] | None:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM rag_index WHERE index_name=? ORDER BY created_at DESC LIMIT 1", (name,)).fetchone()
    return dict(row) if row else None


def ensure_index(name: str = "literature_default") -> dict[str, Any]:
    init_database()
    rag_config = load_config().get("rag", {})
    embedding = rag_config.get("embedding") or {}
    provider = str(embedding.get("provider") or "mock")
    model = str(embedding.get("model") or "deterministic-mock-v1")
    dimension = int(embedding.get("dimension") or 64)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM rag_index
            WHERE index_name=? AND embedding_provider=? AND embedding_model=?
              AND embedding_dimension=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (name, provider, model, dimension),
        ).fetchone()
    if row:
        return dict(row)
    return create_index({"index_name": name})


def index_rag_document(rag_doc_id: str, index_name: str = "literature_default") -> dict[str, Any]:
    """Materialize and index reviewed knowledge; never report success for a flag-only update."""
    init_database()
    now = utc_now_iso()
    job = {
        "job_id": stable_id("ragjob", rag_doc_id, index_name, now, uuid.uuid4().hex),
        "rag_doc_id": rag_doc_id,
        "index_name": index_name,
        "status": "running",
        "started_at": now,
        "finished_at": None,
        "error_message": None,
    }
    canonical: dict[str, str] | None = None
    index_result: dict[str, Any] | None = None
    try:
        canonical = materialize_rag_document(rag_doc_id)
        index = ensure_index(index_name)
        index_result = index_pending_chunks(index["index_id"])
        with get_connection() as conn:
            entry = conn.execute(
                "SELECT status FROM rag_index_entry WHERE index_id=? AND chunk_id=?",
                (index["index_id"], canonical["chunk_id"]),
            ).fetchone()
        fully_indexed = bool(entry and entry["status"] == "indexed")
        job["status"] = "success" if fully_indexed else "partial"
        if not fully_indexed:
            job["error_message"] = "vector embedding unavailable; lexical index is searchable"
    except Exception as exc:  # noqa: BLE001 - failure is persisted for retry/doctor
        job["status"] = "failed"
        job["error_message"] = type(exc).__name__
    job["finished_at"] = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE rag_document SET indexed=?,index_name=? WHERE rag_doc_id=?",
            (1 if job["status"] == "success" else 0, index_name, rag_doc_id),
        )
        conn.execute(
            """
            INSERT INTO rag_index_job VALUES (
              :job_id,:rag_doc_id,:index_name,:status,:started_at,:finished_at,:error_message
            )
            """,
            job,
        )
        conn.commit()
    return {**job, "canonical_document": canonical, "index_result": index_result}


def _embedding_for_index(index: dict[str, Any]):
    config = json.loads(index.get("config_json") or "{}")
    options = config.get("embedding") or {}
    return build_embedding_provider(
        str(index.get("embedding_provider") or options.get("provider") or "mock"),
        str(index.get("embedding_model") or options.get("model") or "deterministic-mock-v1"),
        int(index.get("embedding_dimension") or options.get("dimension") or 64),
        options,
    )
