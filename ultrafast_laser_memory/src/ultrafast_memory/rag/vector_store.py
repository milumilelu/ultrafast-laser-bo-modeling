from __future__ import annotations

import json
import math
from collections import OrderedDict
from threading import Lock
from typing import Any

import numpy as np

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.config import get_database_path
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.rag.metadata_filter import matches_filters


_VECTOR_CORPUS_CACHE: OrderedDict[
    tuple[str, str, str], tuple[tuple[dict[str, Any], ...], np.ndarray, np.ndarray]
] = OrderedDict()
_VECTOR_CORPUS_LOCK = Lock()
_VECTOR_CORPUS_CACHE_SIZE = 8


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
        rows, matrix, norms = self._corpus()
        if not rows or matrix.size == 0 or matrix.shape[1] != len(vector):
            return []
        query = np.asarray(vector, dtype=np.float64)
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0:
            return []
        denominators = norms * query_norm
        scores = np.divide(
            matrix @ query,
            denominators,
            out=np.zeros(len(rows), dtype=np.float64),
            where=denominators != 0,
        )
        hits = []
        for index in np.argsort(scores)[::-1]:
            item = dict(rows[int(index)])
            if not matches_filters(item, filters):
                continue
            item["score"] = float(scores[int(index)])
            hits.append(item)
            if len(hits) >= top_k:
                break
        return hits

    def _corpus(self) -> tuple[tuple[dict[str, Any], ...], np.ndarray, np.ndarray]:
        with get_connection() as conn:
            index = conn.execute(
                "SELECT updated_at FROM rag_index WHERE index_id=?", (self.index_id,)
            ).fetchone()
            revision = str(index["updated_at"] if index else "missing")
            key = (str(get_database_path()), self.index_id, revision)
            with _VECTOR_CORPUS_LOCK:
                cached = _VECTOR_CORPUS_CACHE.get(key)
                if cached is not None:
                    _VECTOR_CORPUS_CACHE.move_to_end(key)
                    return cached
            rows = conn.execute(
                """
                SELECT e.chunk_id,e.vector_ref,c.* FROM rag_index_entry e
                JOIN literature_chunk c ON c.chunk_id=e.chunk_id
                WHERE e.index_id=? AND e.status='indexed' AND c.active=1
                """,
                (self.index_id,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        vectors: list[list[float]] = []
        for row in rows:
            item = dict(row)
            try:
                stored = json.loads(item.pop("vector_ref") or "[]")
            except json.JSONDecodeError:
                continue
            if not isinstance(stored, list) or not stored:
                continue
            records.append(item)
            vectors.append(stored)
        try:
            matrix = np.asarray(vectors, dtype=np.float64)
            if matrix.ndim != 2:
                raise ValueError("vector corpus is not rectangular")
        except (TypeError, ValueError):
            records, vectors = [], []
            matrix = np.empty((0, 0), dtype=np.float64)
        value = (tuple(records), matrix, np.linalg.norm(matrix, axis=1))
        with _VECTOR_CORPUS_LOCK:
            _VECTOR_CORPUS_CACHE[key] = value
            _VECTOR_CORPUS_CACHE.move_to_end(key)
            while len(_VECTOR_CORPUS_CACHE) > _VECTOR_CORPUS_CACHE_SIZE:
                _VECTOR_CORPUS_CACHE.popitem(last=False)
        return value

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
