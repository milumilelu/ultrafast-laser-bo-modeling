from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ultrafast_memory.core.config import load_config, resolve_path
from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection
from ultrafast_memory.literature.canonicalizer import normalize_doi, normalize_title
from ultrafast_memory.literature.chunk_builder import build_chunks
from ultrafast_memory.literature.deduplicator import canonical_paper_id, find_canonical_paper
from ultrafast_memory.literature.inventory import discover_inventory, inventory_summary
from ultrafast_memory.literature.quality import build_quality_report
from ultrafast_memory.literature.raw_pdf_loader import parse_pdf
from ultrafast_memory.literature.section_parser import parse_sections
from ultrafast_memory.literature.source_classifier import classify_source_root, discover_structured_roots
from ultrafast_memory.literature.structured_loader import load_structured_deliverables


def inventory_literature(root: str) -> dict:
    records = discover_inventory(root)
    summary = inventory_summary(records)
    return {"root": str(Path(root).expanduser().resolve()), **summary, "records": [row.model_dump(mode="json") for row in records]}


def plan_ingestion(root: str) -> dict:
    inventory = inventory_literature(root)
    classification = classify_source_root(root)
    return {
        **classification,
        "discovered_count": inventory["discovered_count"],
        "asset_counts": inventory["asset_counts"],
        "duplicate_file_count": inventory["duplicate_file_count"],
        "structured_roots": [str(path) for path in discover_structured_roots(root)],
    }


def ingest_literature(root: str, mode: str = "auto", force: bool = False) -> dict:
    init_database()
    root_path = Path(root).expanduser().resolve()
    plan = plan_ingestion(str(root_path))
    selected_mode = plan["recommended_mode"] if mode == "auto" else mode
    now = utc_now_iso()
    job_id = stable_id("literature_job", str(root_path), selected_mode, now, uuid.uuid4().hex)
    result = {
        "job_id": job_id,
        "root_path": str(root_path),
        "mode": selected_mode,
        "status": "running",
        "discovered_count": plan["discovered_count"],
        "ingested_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "needs_review_count": 0,
        "needs_ocr_count": 0,
        "paper_count": 0,
        "section_count": 0,
        "chunk_count": 0,
        "candidate_count": 0,
        "errors": [],
    }
    _insert_job(result, now)
    records = discover_inventory(root_path)
    with get_connection() as conn:
        for record in records:
            if record.asset_type != "raw_pdf":
                inserted = _register_artifact(
                    conn,
                    {
                        "artifact_id": stable_id("lart", record.sha256, record.asset_type),
                        "original_path": record.path,
                        "archived_path": record.path,
                        "asset_type": record.asset_type,
                        "sha256": record.sha256,
                        "file_size_bytes": record.file_size_bytes,
                        "parent_root": record.related_root,
                        "parse_status": "registered",
                        "parser_name": "inventory",
                        "parser_version": "1.0.0",
                        "error_message": "",
                        "discovered_at": record.discovered_at,
                        "imported_at": now,
                    },
                )
                result["ingested_count" if inserted else "skipped_count"] += 1
        conn.commit()
    paper_map: dict[str, str] = {}
    if selected_mode in {"structured_only", "structured_first_with_pdf_backfill", "mixed_unresolved"}:
        for structured_root in discover_structured_roots(root_path):
            try:
                loaded = load_structured_deliverables(structured_root)
                result["errors"].extend(loaded["errors"])
                result["failed_count"] += len(loaded["errors"])
                artifact_id = _structured_artifact_id(structured_root)
                with get_connection() as conn:
                    for card_model in loaded["cards"]:
                        card = card_model.model_dump(mode="json")
                        paper, created, needs_review = _upsert_paper(conn, card, artifact_id, source_role="structured_metadata")
                        paper_map[card["paper_id"]] = paper["paper_id"]
                        result["paper_count"] += int(created)
                        result["needs_review_count"] += int(needs_review)
                    candidates = loaded["candidates"] or loaded["claims"]
                    for candidate in candidates:
                        source_paper_id = str(candidate.get("paper_id") or "")
                        canonical_id = paper_map.get(source_paper_id, source_paper_id or None)
                        if _ingest_candidate(conn, candidate, canonical_id):
                            result["candidate_count"] += 1
                    conn.commit()
            except Exception as exc:
                result["failed_count"] += 1
                result["errors"].append(f"{structured_root}: {exc}")
    if selected_mode in {"raw_pdf_only", "structured_first_with_pdf_backfill", "mixed_unresolved"}:
        cfg = load_config()
        archive_dir = resolve_path(cfg.get("literature", {}).get("archive_dir", "data/literature_archive"))
        chunk_cfg = cfg.get("rag", {}).get("chunking", {})
        pdf_records = [record for record in records if record.asset_type == "raw_pdf"]
        seen_sha: set[str] = set()
        for record in pdf_records:
            if record.sha256 in seen_sha:
                result["skipped_count"] += 1
                continue
            seen_sha.add(record.sha256)
            try:
                if not force:
                    with get_connection() as conn:
                        existing_artifact = conn.execute(
                            "SELECT artifact_id FROM literature_artifact WHERE sha256=? AND asset_type='raw_pdf'",
                            (record.sha256,),
                        ).fetchone()
                        if existing_artifact:
                            linked = conn.execute(
                                "SELECT 1 FROM literature_paper_source WHERE artifact_id=? LIMIT 1",
                                (existing_artifact["artifact_id"],),
                            ).fetchone()
                            chunked = conn.execute(
                                "SELECT 1 FROM literature_chunk WHERE artifact_id=? LIMIT 1",
                                (existing_artifact["artifact_id"],),
                            ).fetchone()
                            status = conn.execute(
                                "SELECT parse_status FROM literature_artifact WHERE artifact_id=?",
                                (existing_artifact["artifact_id"],),
                            ).fetchone()
                            if linked and (chunked or (status and status["parse_status"] == "needs_ocr")):
                                result["skipped_count"] += 1
                                continue
                parsed = parse_pdf(record.path, archive_dir)
                with get_connection() as conn:
                    artifact_created = _register_artifact(conn, parsed.artifact, force=force)
                    if force:
                        conn.execute(
                            "DELETE FROM rag_index_entry WHERE chunk_id IN (SELECT chunk_id FROM literature_chunk WHERE artifact_id=?)",
                            (parsed.artifact["artifact_id"],),
                        )
                        conn.execute("DELETE FROM literature_chunk WHERE artifact_id=?", (parsed.artifact["artifact_id"],))
                        conn.execute("DELETE FROM literature_section WHERE artifact_id=?", (parsed.artifact["artifact_id"],))
                    if not artifact_created and not force:
                        existing_link = conn.execute(
                            "SELECT paper_id FROM literature_paper_source WHERE artifact_id = ?",
                            (parsed.artifact["artifact_id"],),
                        ).fetchone()
                        existing_chunks = conn.execute(
                            "SELECT count(*) AS count FROM literature_chunk WHERE artifact_id = ?",
                            (parsed.artifact["artifact_id"],),
                        ).fetchone()["count"]
                        if existing_link and existing_chunks:
                            result["skipped_count"] += 1
                            conn.commit()
                            continue
                    if parsed.parse_status == "failed":
                        result["failed_count"] += 1
                        result["errors"].append(f"{record.path}: {parsed.error_message}")
                        conn.commit()
                        continue
                    paper, created, needs_review = _upsert_paper(
                        conn,
                        parsed.metadata,
                        parsed.artifact["artifact_id"],
                        source_role="original_pdf",
                        prefer_existing=True,
                    )
                    result["paper_count"] += int(created)
                    result["needs_review_count"] += int(needs_review)
                    if parsed.parse_status == "needs_ocr":
                        result["needs_ocr_count"] += 1
                        conn.commit()
                        continue
                    sections = parse_sections(paper["paper_id"], parsed.artifact["artifact_id"], parsed.pages)
                    for section in sections:
                        values = section.model_dump(mode="json")
                        values["created_at"] = utc_now_iso()
                        cursor = conn.execute(
                            """
                            INSERT OR IGNORE INTO literature_section
                            (section_id,paper_id,artifact_id,section_type,section_title,page_start,page_end,text,text_hash,parser_version,created_at)
                            VALUES (:section_id,:paper_id,:artifact_id,:section_type,:section_title,:page_start,:page_end,:text,:text_hash,:parser_version,:created_at)
                            """,
                            values,
                        )
                        result["section_count"] += max(cursor.rowcount, 0)
                    chunks = build_chunks(
                        _paper_for_chunk(paper),
                        sections,
                        target_tokens=int(chunk_cfg.get("target_tokens", 450)),
                        min_tokens=int(chunk_cfg.get("min_tokens", 120)),
                        max_tokens=int(chunk_cfg.get("max_tokens", 700)),
                        overlap_tokens=int(chunk_cfg.get("overlap_tokens", 80)),
                        include_references=bool(cfg.get("literature", {}).get("include_references_section", False)),
                    )
                    for chunk in chunks:
                        values = chunk.model_dump(mode="json")
                        values["metadata_json"] = json.dumps(values.pop("metadata"), ensure_ascii=False)
                        values["active"] = int(values["active"])
                        values["created_at"] = utc_now_iso()
                        values["updated_at"] = values["created_at"]
                        cursor = conn.execute(
                            """
                            INSERT OR IGNORE INTO literature_chunk
                            (chunk_id,paper_id,section_id,artifact_id,chunk_index,page_start,page_end,section_type,section_title,content,content_hash,token_estimate,metadata_json,evidence_level,review_status,active,created_at,updated_at)
                            VALUES (:chunk_id,:paper_id,:section_id,:artifact_id,:chunk_index,:page_start,:page_end,:section_type,:section_title,:content,:content_hash,:token_estimate,:metadata_json,:evidence_level,:review_status,:active,:created_at,:updated_at)
                            """,
                            values,
                        )
                        result["chunk_count"] += max(cursor.rowcount, 0)
                    result["ingested_count"] += int(artifact_created)
                    conn.commit()
            except Exception as exc:
                result["failed_count"] += 1
                result["errors"].append(f"{record.path}: {exc}")
    result["status"] = "completed_with_errors" if result["failed_count"] else "completed"
    result["quality_report"] = build_quality_report()
    _finish_job(result)
    return result


def get_ingestion_status(job_id: str) -> dict:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM rag_ingestion_job WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        raise ValueError(f"ingestion job not found: {job_id}")
    result = dict(row)
    result["config"] = json.loads(result.pop("config_json") or "{}")
    return result


def list_papers(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    init_database()
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM literature_paper ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()]


def get_paper(paper_id: str) -> dict[str, Any]:
    init_database()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM literature_paper WHERE paper_id = ?", (paper_id,)).fetchone()
        if not row:
            raise ValueError(f"paper not found: {paper_id}")
        result = dict(row)
        result["sources"] = [dict(item) for item in conn.execute("SELECT * FROM literature_paper_source WHERE paper_id = ?", (paper_id,)).fetchall()]
        return result


def get_paper_chunks(paper_id: str) -> list[dict[str, Any]]:
    init_database()
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM literature_chunk WHERE paper_id = ? ORDER BY chunk_index", (paper_id,)).fetchall()]


def _register_artifact(conn, artifact: dict[str, Any], force: bool = False) -> bool:
    existing = conn.execute(
        "SELECT artifact_id FROM literature_artifact WHERE sha256 = ? AND asset_type = ?",
        (artifact["sha256"], artifact["asset_type"]),
    ).fetchone()
    if existing:
        if force:
            conn.execute(
                """
                UPDATE literature_artifact SET archived_path=?, parse_status=?, parser_name=?, parser_version=?,
                error_message=?, imported_at=? WHERE artifact_id=?
                """,
                (
                    artifact.get("archived_path"), artifact.get("parse_status"), artifact.get("parser_name"),
                    artifact.get("parser_version"), artifact.get("error_message"), artifact.get("imported_at"), existing["artifact_id"],
                ),
            )
        artifact["artifact_id"] = existing["artifact_id"]
        return False
    conn.execute(
        """
        INSERT INTO literature_artifact
        (artifact_id,original_path,archived_path,asset_type,sha256,file_size_bytes,parent_root,parse_status,parser_name,parser_version,error_message,discovered_at,imported_at)
        VALUES (:artifact_id,:original_path,:archived_path,:asset_type,:sha256,:file_size_bytes,:parent_root,:parse_status,:parser_name,:parser_version,:error_message,:discovered_at,:imported_at)
        """,
        artifact,
    )
    return True


def _structured_artifact_id(root: Path) -> str | None:
    for name in ("literature_cards.jsonl", "paper_table.csv"):
        path = root / name
        if path.exists():
            from ultrafast_memory.literature.inventory import sha256_path

            return stable_id("lart", sha256_path(path), "structured_literature_card" if name.endswith("jsonl") else "structured_paper_table")
    return None


PAPER_FIELDS = [
    "authors", "year", "doi", "source", "url", "scenario_id", "material", "material_grade",
    "component_type", "process_type", "laser_type", "wavelength_nm", "pulse_width_fs",
    "power_or_energy", "frequency_kHz", "scan_speed_mm_s", "beam_shape", "environment",
]


def _upsert_paper(conn, metadata: dict[str, Any], artifact_id: str | None, source_role: str, prefer_existing: bool = False):
    # A structured CSV/JSONL artifact can describe many papers. Only a PDF artifact
    # has a one-artifact-to-one-paper identity suitable for SHA-level paper lookup.
    dedup_artifact_id = artifact_id if source_role == "original_pdf" else None
    match = find_canonical_paper(conn, metadata, dedup_artifact_id)
    now = utc_now_iso()
    if match["paper"]:
        paper = match["paper"]
        updates: dict[str, Any] = {}
        for field in PAPER_FIELDS:
            incoming = metadata.get(field)
            if incoming in (None, ""):
                continue
            if paper.get(field) in (None, "") or not prefer_existing:
                updates[field] = normalize_doi(str(incoming)) if field == "doi" else incoming
            elif str(paper.get(field)) != str(incoming):
                updates["review_status"] = "needs_review"
        title = metadata.get("title") or metadata.get("canonical_title")
        if title and (not paper.get("canonical_title") or not prefer_existing):
            updates["canonical_title"] = title
            updates["normalized_title"] = normalize_title(str(title))
        if match["needs_review"]:
            updates["review_status"] = "needs_review"
        if updates:
            updates["updated_at"] = now
            assignments = ", ".join(f"{key} = :{key}" for key in updates)
            conn.execute(f"UPDATE literature_paper SET {assignments} WHERE paper_id = :paper_id", {**updates, "paper_id": paper["paper_id"]})
            paper.update(updates)
        created = False
    else:
        requested_id = canonical_paper_id(metadata)
        collision = conn.execute("SELECT normalized_title FROM literature_paper WHERE paper_id = ?", (requested_id,)).fetchone()
        paper_id = requested_id
        if collision and collision["normalized_title"] != normalize_title(str(metadata.get("title") or "")):
            paper_id = stable_id("paper", requested_id, normalize_title(str(metadata.get("title") or "")), metadata.get("year"))
        paper = {
            "paper_id": paper_id,
            "canonical_title": metadata.get("title") or metadata.get("canonical_title") or "",
            "normalized_title": normalize_title(str(metadata.get("title") or metadata.get("canonical_title") or "")),
            **{field: metadata.get(field) for field in PAPER_FIELDS},
            "doi": normalize_doi(str(metadata.get("doi") or "")),
            "geometry_json": json.dumps(metadata.get("geometry") or {}, ensure_ascii=False),
            "quality_metrics_json": json.dumps(metadata.get("quality_metrics") or {}, ensure_ascii=False),
            "defects_json": json.dumps(metadata.get("defects") or [], ensure_ascii=False),
            "measurement_methods_json": json.dumps(metadata.get("measurement_methods") or [], ensure_ascii=False),
            "usable_for_json": json.dumps(metadata.get("usable_for") or ["literature_background", "evidence_retrieval"], ensure_ascii=False),
            "not_usable_for_json": json.dumps(metadata.get("not_usable_for") or ["direct_parameter_recommendation", "BO_training"], ensure_ascii=False),
            "evidence_level": metadata.get("evidence_level") or "literature_evidence_candidate",
            "review_status": "needs_review" if match["needs_review"] else metadata.get("review_status") or "pending_review",
            "canonical_artifact_id": artifact_id,
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """
            INSERT INTO literature_paper VALUES
            (:paper_id,:canonical_title,:normalized_title,:authors,:year,:doi,:source,:url,:scenario_id,:material,:material_grade,:component_type,:process_type,:laser_type,:wavelength_nm,:pulse_width_fs,:power_or_energy,:frequency_kHz,:scan_speed_mm_s,:beam_shape,:environment,:geometry_json,:quality_metrics_json,:defects_json,:measurement_methods_json,:usable_for_json,:not_usable_for_json,:evidence_level,:review_status,:canonical_artifact_id,:created_at,:updated_at)
            """,
            paper,
        )
        created = True
    if artifact_id:
        conn.execute(
            """
            INSERT OR IGNORE INTO literature_paper_source
            (link_id,paper_id,artifact_id,source_role,version_label,is_canonical,created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (stable_id("paper_source", paper["paper_id"], artifact_id), paper["paper_id"], artifact_id, source_role, "", int(paper.get("canonical_artifact_id") == artifact_id), now),
        )
    return paper, created, paper.get("review_status") == "needs_review"


def _ingest_candidate(conn, candidate: dict[str, Any], paper_id: str | None) -> bool:
    claim = str(candidate.get("claim") or "").strip()
    if not claim:
        return False
    candidate_id = str(candidate.get("candidate_id") or candidate.get("claim_id") or stable_id("kc", paper_id, claim))
    if conn.execute("SELECT 1 FROM knowledge_candidate WHERE candidate_id = ?", (candidate_id,)).fetchone():
        return False
    confidence = candidate.get("confidence")
    if isinstance(confidence, str):
        confidence = {"low": 0.3, "medium": 0.6, "high": 0.85}.get(confidence.lower(), 0.3)
    record = {
        "candidate_id": candidate_id,
        "source_id": candidate.get("source_id"),
        "claim": claim,
        "material": candidate.get("material"),
        "process_type": candidate.get("process_type"),
        "component_type": candidate.get("component_type"),
        "parameter_json": json.dumps(candidate.get("parameter_json") or {}, ensure_ascii=False),
        "condition_json": json.dumps(candidate.get("condition_json") or {}, ensure_ascii=False),
        "usable_for_json": json.dumps(candidate.get("usable_for_json") or candidate.get("usable_for") or ["literature_background"], ensure_ascii=False),
        "not_usable_for_json": json.dumps(candidate.get("not_usable_for_json") or candidate.get("not_usable_for") or ["direct_parameter_recommendation", "BO_training"], ensure_ascii=False),
        "evidence_type": candidate.get("evidence_type") or "paper_evidence",
        "confidence": float(confidence or 0.3),
        "status": "candidate",
        "review_status": "pending_review",
        "risk_level": candidate.get("risk_level") or "medium",
        "suggested_action": candidate.get("suggested_action") or "accept_as_literature_evidence",
        "conflict_flag": 0,
        "duplicate_of": None,
        "source_quality_score": None,
        "created_at": candidate.get("created_at") or utc_now_iso(),
        "reviewed_by": None,
        "review_comment": None,
        "paper_id": paper_id,
        "evidence_level": candidate.get("evidence_level") or "literature_evidence_candidate",
        "extraction_method": candidate.get("extraction_method") or "structured_import",
    }
    conn.execute(
        """
        INSERT INTO knowledge_candidate
        (candidate_id,source_id,claim,material,process_type,component_type,parameter_json,condition_json,usable_for_json,not_usable_for_json,evidence_type,confidence,status,review_status,risk_level,suggested_action,conflict_flag,duplicate_of,source_quality_score,created_at,reviewed_by,review_comment,paper_id,evidence_level,extraction_method)
        VALUES (:candidate_id,:source_id,:claim,:material,:process_type,:component_type,:parameter_json,:condition_json,:usable_for_json,:not_usable_for_json,:evidence_type,:confidence,:status,:review_status,:risk_level,:suggested_action,:conflict_flag,:duplicate_of,:source_quality_score,:created_at,:reviewed_by,:review_comment,:paper_id,:evidence_level,:extraction_method)
        """,
        record,
    )
    review_id = stable_id("review", candidate_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO knowledge_review_task
        (review_id,candidate_id,review_status,priority,risk_level,assigned_to,created_at,updated_at,due_at,auto_suggestion,review_comment)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (review_id, candidate_id, "pending_review", "normal", record["risk_level"], None, utc_now_iso(), utc_now_iso(), None, record["suggested_action"], None),
    )
    return True


def _paper_for_chunk(paper: dict[str, Any]) -> dict[str, Any]:
    result = dict(paper)
    result["title"] = paper.get("canonical_title")
    result["source_id"] = paper.get("canonical_artifact_id")
    for source, target, default in (
        ("usable_for_json", "usable_for", []),
        ("not_usable_for_json", "not_usable_for", []),
    ):
        result[target] = json.loads(paper.get(source) or json.dumps(default))
    return result


def _insert_job(result: dict[str, Any], started_at: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rag_ingestion_job VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                result["job_id"], result["root_path"], result["mode"], "running", result["discovered_count"],
                0, 0, 0, 0, started_at, None, None, json.dumps({}, ensure_ascii=False),
            ),
        )
        conn.commit()


def _finish_job(result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE rag_ingestion_job SET status=?,ingested_count=?,skipped_count=?,failed_count=?,needs_review_count=?,finished_at=?,error_summary=?,config_json=? WHERE job_id=?
            """,
            (
                result["status"], result["ingested_count"], result["skipped_count"], result["failed_count"],
                result["needs_review_count"], utc_now_iso(), "\n".join(result["errors"][:100]),
                json.dumps({"needs_ocr_count": result["needs_ocr_count"], "paper_count": result["paper_count"], "section_count": result["section_count"], "chunk_count": result["chunk_count"], "candidate_count": result["candidate_count"]}, ensure_ascii=False),
                result["job_id"],
            ),
        )
        conn.commit()
