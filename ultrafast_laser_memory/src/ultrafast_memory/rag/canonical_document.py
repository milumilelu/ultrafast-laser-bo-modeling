from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def materialize_rag_document(rag_doc_id: str) -> dict[str, str]:
    """Project one reviewed RAG document into the canonical chunk/index source tables."""
    init_database()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM rag_document WHERE rag_doc_id = ?", (rag_doc_id,)
        ).fetchone()
    if not row:
        raise ValueError(f"rag document not found: {rag_doc_id}")

    document = dict(row)
    metadata = _loads(document.get("metadata_json"))
    content = str(document.get("content") or "").strip()
    if not content:
        raise ValueError(f"rag document has no content: {rag_doc_id}")
    now = utc_now_iso()
    paper_id = stable_id("paper", "reviewed_knowledge", rag_doc_id)
    section_id = stable_id("section", paper_id, "reviewed_claim")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    chunk_id = stable_id("chunk", paper_id, content_hash)
    title = str(document.get("title") or metadata.get("title") or rag_doc_id)
    evidence_level = str(metadata.get("evidence_level") or "reviewed_background")
    review_status = "accepted"
    usable_for = _as_list(metadata.get("usable_for"))
    not_usable_for = _as_list(metadata.get("not_usable_for"))
    chunk_metadata = {
        **metadata,
        "paper_id": paper_id,
        "rag_doc_id": rag_doc_id,
        "source_type": "reviewed_knowledge",
        "title": title,
        "material": metadata.get("material"),
        "process_type": metadata.get("process_type"),
        "component_type": metadata.get("component_type"),
        "evidence_level": evidence_level,
        "review_status": review_status,
        "review_action_status": metadata.get("review_status"),
        "usable_for": usable_for,
        "not_usable_for": not_usable_for,
        "section_type": "reviewed_claim",
        "section_title": "Reviewed knowledge claim",
        "page_start": 1,
        "page_end": 1,
    }
    paper = {
        "paper_id": paper_id,
        "canonical_title": title,
        "normalized_title": re.sub(r"\s+", " ", title).strip().casefold(),
        "authors": metadata.get("authors"),
        "year": metadata.get("year"),
        "doi": metadata.get("doi"),
        "source": "reviewed_knowledge",
        "url": metadata.get("url"),
        "scenario_id": metadata.get("scenario_id"),
        "material": metadata.get("material"),
        "material_grade": metadata.get("material_grade"),
        "component_type": metadata.get("component_type"),
        "process_type": metadata.get("process_type"),
        "laser_type": metadata.get("laser_type"),
        "wavelength_nm": None,
        "pulse_width_fs": None,
        "power_or_energy": None,
        "frequency_kHz": None,
        "scan_speed_mm_s": None,
        "beam_shape": None,
        "environment": None,
        "geometry_json": json.dumps(metadata.get("geometry") or {}, ensure_ascii=False),
        "quality_metrics_json": json.dumps(metadata.get("quality_metrics") or {}, ensure_ascii=False),
        "defects_json": json.dumps(metadata.get("defects") or [], ensure_ascii=False),
        "measurement_methods_json": json.dumps(
            metadata.get("measurement_methods") or [], ensure_ascii=False
        ),
        "usable_for_json": json.dumps(usable_for, ensure_ascii=False),
        "not_usable_for_json": json.dumps(not_usable_for, ensure_ascii=False),
        "evidence_level": evidence_level,
        "review_status": review_status,
        "canonical_artifact_id": None,
        "created_at": now,
        "updated_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO literature_paper (
              paper_id,canonical_title,normalized_title,authors,year,doi,source,url,
              scenario_id,material,material_grade,component_type,process_type,laser_type,
              wavelength_nm,pulse_width_fs,power_or_energy,frequency_kHz,scan_speed_mm_s,
              beam_shape,environment,geometry_json,quality_metrics_json,defects_json,
              measurement_methods_json,usable_for_json,not_usable_for_json,evidence_level,
              review_status,canonical_artifact_id,created_at,updated_at
            ) VALUES (
              :paper_id,:canonical_title,:normalized_title,:authors,:year,:doi,:source,:url,
              :scenario_id,:material,:material_grade,:component_type,:process_type,:laser_type,
              :wavelength_nm,:pulse_width_fs,:power_or_energy,:frequency_kHz,:scan_speed_mm_s,
              :beam_shape,:environment,:geometry_json,:quality_metrics_json,:defects_json,
              :measurement_methods_json,:usable_for_json,:not_usable_for_json,:evidence_level,
              :review_status,:canonical_artifact_id,:created_at,:updated_at
            ) ON CONFLICT(paper_id) DO UPDATE SET
              canonical_title=excluded.canonical_title, material=excluded.material,
              component_type=excluded.component_type, process_type=excluded.process_type,
              usable_for_json=excluded.usable_for_json,
              not_usable_for_json=excluded.not_usable_for_json,
              evidence_level=excluded.evidence_level, review_status=excluded.review_status,
              updated_at=excluded.updated_at
            """,
            paper,
        )
        conn.execute(
            "UPDATE literature_chunk SET active=0,updated_at=? WHERE paper_id=? AND chunk_id<>?",
            (now, paper_id, chunk_id),
        )
        conn.execute(
            """
            INSERT INTO literature_section (
              section_id,paper_id,artifact_id,section_type,section_title,page_start,page_end,
              text,text_hash,parser_version,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(section_id) DO UPDATE SET
              text=excluded.text,text_hash=excluded.text_hash,section_title=excluded.section_title
            """,
            (
                section_id, paper_id, None, "reviewed_claim", "Reviewed knowledge claim",
                1, 1, content, content_hash, "canonical-knowledge-v1", now,
            ),
        )
        conn.execute(
            """
            INSERT INTO literature_chunk (
              chunk_id,paper_id,section_id,artifact_id,chunk_index,page_start,page_end,
              section_type,section_title,content,content_hash,token_estimate,metadata_json,
              evidence_level,review_status,active,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chunk_id) DO UPDATE SET
              content=excluded.content,content_hash=excluded.content_hash,
              metadata_json=excluded.metadata_json,evidence_level=excluded.evidence_level,
              review_status=excluded.review_status,active=1,updated_at=excluded.updated_at
            """,
            (
                chunk_id, paper_id, section_id, None, 0, 1, 1, "reviewed_claim",
                "Reviewed knowledge claim", content, content_hash, _estimate_tokens(content),
                json.dumps(chunk_metadata, ensure_ascii=False), evidence_level, review_status,
                1, now, now,
            ),
        )
        conn.commit()
    return {"paper_id": paper_id, "section_id": section_id, "chunk_id": chunk_id}


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        return [value]
    return []


def _estimate_tokens(text: str) -> int:
    latin = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin + cjk
