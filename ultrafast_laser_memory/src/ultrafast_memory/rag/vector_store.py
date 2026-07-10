from __future__ import annotations

import json
import math
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.metadata_filter import matches_filters


class BaseVectorStore:
    def upsert(self, entries: list[dict]) -> list[dict]:
        raise NotImplementedError

    def query(self, vector: list[float], top_k: int, filters: dict | None = None) -> list[dict]:
        raise NotImplementedError

    def delete(self, chunk_ids: list[str]) -> None:
        raise NotImplementedError


class InMemoryVectorStore(BaseVectorStore):
    def __init__(self):
        self.entries: dict[str, dict] = {}

    def upsert(self, entries: list[dict]) -> list[dict]:
        for entry in entries:
            self.entries[entry["chunk_id"]] = dict(entry)
        return entries

    def query(self, vector: list[float], top_k: int, filters: dict | None = None) -> list[dict]:
        hits = []
        for entry in self.entries.values():
            score = cosine_similarity(vector, entry["vector"])
            hits.append({**entry, "score": score})
        return sorted(hits, key=lambda row: row["score"], reverse=True)[:top_k]

    def delete(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self.entries.pop(chunk_id, None)


class SQLiteVectorStore(BaseVectorStore):
    def __init__(self, index_id: str):
        self.index_id = index_id

    def upsert(self, entries: list[dict]) -> list[dict]:
        now = utc_now_iso()
        records = [
            (
                stable_id("rag_entry", self.index_id, entry["chunk_id"]), self.index_id,
                entry["chunk_id"], json.dumps(entry["vector"]), entry.get("lexical_ref"),
                entry.get("content_hash"), now, "vector_indexed", None,
            )
            for entry in entries
        ]
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO rag_index_entry
                (entry_id,index_id,chunk_id,vector_ref,lexical_ref,content_hash,indexed_at,status,error_message)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(index_id,chunk_id) DO UPDATE SET
                vector_ref=excluded.vector_ref, content_hash=excluded.content_hash,
                indexed_at=excluded.indexed_at, status='vector_indexed', error_message=NULL
                """,
                records,
            )
            conn.commit()
        return entries

    def query(self, vector: list[float], top_k: int, filters: dict | None = None) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT e.chunk_id,e.vector_ref,c.* FROM rag_index_entry e
                JOIN literature_chunk c ON c.chunk_id=e.chunk_id
                WHERE e.index_id=? AND e.status='indexed' AND c.active=1
                """,
                (self.index_id,),
            ).fetchall()
        hits = []
        for row in rows:
            item = dict(row)
            try:
                stored = json.loads(item.pop("vector_ref") or "[]")
            except json.JSONDecodeError:
                continue
            if not matches_filters(item, filters):
                continue
            item["score"] = cosine_similarity(vector, stored)
            hits.append(item)
        return sorted(hits, key=lambda row: row["score"], reverse=True)[:top_k]

    def delete(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        with get_connection() as conn:
            conn.executemany("DELETE FROM rag_index_entry WHERE index_id=? AND chunk_id=?", [(self.index_id, item) for item in chunk_ids])
            conn.commit()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0
