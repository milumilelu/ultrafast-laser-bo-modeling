from __future__ import annotations

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def index_experience_candidate(candidate_id: str) -> None:
    return None


def search_memory(query: str, filters: dict | None = None) -> list:
    return []


def index_rag_document(rag_doc_id: str, index_name: str = "default") -> dict:
    init_database()
    now = utc_now_iso()
    job = {
        "job_id": stable_id("ragjob", rag_doc_id, index_name, now),
        "rag_doc_id": rag_doc_id,
        "index_name": index_name,
        "status": "success",
        "started_at": now,
        "finished_at": now,
        "error_message": None,
    }
    with get_connection() as conn:
        conn.execute(
            "UPDATE rag_document SET indexed = 1, index_name = ? WHERE rag_doc_id = ?",
            (index_name, rag_doc_id),
        )
        conn.execute(
            """
            INSERT INTO rag_index_job VALUES (
              :job_id, :rag_doc_id, :index_name, :status, :started_at, :finished_at, :error_message
            )
            """,
            job,
        )
        conn.commit()
    return job
