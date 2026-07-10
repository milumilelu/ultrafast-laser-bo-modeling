from __future__ import annotations

import re
from typing import Any

from ultrafast_memory.db.session import get_connection


class SQLiteLexicalIndex:
    def __init__(self):
        self.fts5 = self._ensure_table()

    def _ensure_table(self) -> bool:
        with get_connection() as conn:
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS literature_chunk_fts USING fts5(
                        chunk_id UNINDEXED, content, title, material, material_grade,
                        process_type, component_type, section_title
                    )
                    """
                )
                conn.commit()
                return True
            except Exception:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS literature_chunk_keyword (
                        chunk_id TEXT PRIMARY KEY, content TEXT, title TEXT, material TEXT,
                        material_grade TEXT, process_type TEXT, component_type TEXT, section_title TEXT
                    )
                    """
                )
                conn.commit()
                return False

    def upsert(self, entries: list[dict[str, Any]]) -> None:
        table = "literature_chunk_fts" if self.fts5 else "literature_chunk_keyword"
        records = [
            (
                entry["chunk_id"], entry.get("content", ""), entry.get("title", ""),
                entry.get("material", ""), entry.get("material_grade", ""),
                entry.get("process_type", ""), entry.get("component_type", ""),
                entry.get("section_title", ""),
            )
            for entry in entries
        ]
        with get_connection() as conn:
            conn.executemany(f"DELETE FROM {table} WHERE chunk_id=?", [(entry["chunk_id"],) for entry in entries])
            conn.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?)", records)
            conn.commit()

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower())
        if not terms:
            return []
        with get_connection() as conn:
            if self.fts5:
                safe_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
                try:
                    rows = conn.execute(
                        """
                        SELECT f.chunk_id, bm25(literature_chunk_fts) AS rank, c.*
                        FROM literature_chunk_fts f JOIN literature_chunk c ON c.chunk_id=f.chunk_id
                        WHERE literature_chunk_fts MATCH ? AND c.active=1
                        ORDER BY rank LIMIT ?
                        """,
                        (safe_query, top_k),
                    ).fetchall()
                    return [{**dict(row), "score": 1.0 / (1.0 + max(float(row["rank"]), 0.0))} for row in rows]
                except Exception:
                    pass
            rows = conn.execute("SELECT * FROM literature_chunk WHERE active=1").fetchall()
        scored = []
        for row in rows:
            item = dict(row)
            haystack = item.get("content", "").lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append({**item, "score": float(score)})
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:top_k]

    def delete(self, chunk_ids: list[str]) -> None:
        table = "literature_chunk_fts" if self.fts5 else "literature_chunk_keyword"
        with get_connection() as conn:
            conn.executemany(f"DELETE FROM {table} WHERE chunk_id=?", [(item,) for item in chunk_ids])
            conn.commit()
