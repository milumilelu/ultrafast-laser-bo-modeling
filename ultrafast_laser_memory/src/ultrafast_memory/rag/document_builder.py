from __future__ import annotations

import json

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def build_rag_document_from_candidate(candidate: dict, source: dict) -> dict:
    init_database()
    rag_doc_id = stable_id("rag", candidate.get("candidate_id"), candidate.get("review_status"), candidate.get("claim"))
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM rag_document WHERE rag_doc_id = ?", (rag_doc_id,)).fetchone()
        if existing:
            return dict(existing)
    content = "\n".join(
        [
            f"来源：{source.get('title') or ''}",
            f"URL：{source.get('url') or ''}",
            f"证据类型：{candidate.get('evidence_type') or ''}",
            f"材料：{candidate.get('material') or ''}",
            f"工艺：{candidate.get('process_type') or ''}",
            f"对象：{candidate.get('component_type') or ''}",
            f"结论：{candidate.get('claim') or ''}",
            f"参数：{json.dumps(candidate.get('parameter') or {}, ensure_ascii=False)}",
            f"条件：{json.dumps(candidate.get('condition') or {}, ensure_ascii=False)}",
            f"适用范围：{candidate.get('usable_for') or []}",
            f"不可用于：{candidate.get('not_usable_for') or []}",
            f"置信度：{candidate.get('confidence')}",
            f"审核状态：{candidate.get('review_status') or ''}",
        ]
    )
    metadata = {
        "source_id": source.get("source_id"),
        "candidate_id": candidate.get("candidate_id"),
        "title": source.get("title"),
        "url": source.get("url"),
        "doi": source.get("doi"),
        "authors": source.get("authors"),
        "evidence_type": candidate.get("evidence_type"),
        "review_status": candidate.get("review_status"),
        "target_level": candidate.get("target_level"),
        "evidence_level": candidate.get("evidence_level"),
        "material": candidate.get("material"),
        "process_type": candidate.get("process_type"),
        "component_type": candidate.get("component_type"),
        "parameter": candidate.get("parameter") or {},
        "condition": candidate.get("condition") or {},
        "usable_for": candidate.get("usable_for") or [],
        "not_usable_for": candidate.get("not_usable_for") or [],
        "confidence": candidate.get("confidence"),
    }
    record = {
        "rag_doc_id": rag_doc_id,
        "source_id": source.get("source_id"),
        "candidate_id": candidate.get("candidate_id"),
        "title": source.get("title") or candidate.get("claim")[:80],
        "content": content,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "indexed": 0,
        "index_name": None,
        "created_at": utc_now_iso(),
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rag_document VALUES (
              :rag_doc_id, :source_id, :candidate_id, :title, :content,
              :metadata_json, :indexed, :index_name, :created_at
            )
            """,
            record,
        )
        conn.commit()
    return record
