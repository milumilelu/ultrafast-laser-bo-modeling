from __future__ import annotations

import hashlib

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def register_external_source(source: dict) -> dict:
    init_database()
    title = source.get("title") or ""
    url = source.get("url") or ""
    snippet = source.get("snippet") or source.get("raw_snippet") or ""
    content_hash = hashlib.sha256(f"{title}\n{url}\n{snippet}".encode("utf-8")).hexdigest()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM external_source_artifact WHERE url = ? OR content_hash = ?",
            (url, content_hash),
        ).fetchone()
        if existing:
            return dict(existing)
        record = {
            "source_id": stable_id("src", url or title, content_hash),
            "source_type": source.get("source_type") or "web_page",
            "title": title,
            "url": url,
            "doi": source.get("doi"),
            "authors": source.get("authors"),
            "published_at": source.get("published_at"),
            "accessed_at": utc_now_iso(),
            "provider": source.get("provider") or "mock_web_search",
            "raw_snippet": snippet,
            "local_snapshot_path": source.get("local_snapshot_path"),
            "content_hash": content_hash,
            "credibility_score": float(source.get("credibility_score") or 0.5),
            "status": source.get("status") or "fetched",
        }
        conn.execute(
            """
            INSERT INTO external_source_artifact VALUES (
              :source_id, :source_type, :title, :url, :doi, :authors, :published_at,
              :accessed_at, :provider, :raw_snippet, :local_snapshot_path,
              :content_hash, :credibility_score, :status
            )
            """,
            record,
        )
        conn.commit()
    return record
