from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ultrafast_memory.core.config import get_project_root
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
VALID_REVIEW = {"pending_review", "needs_review", "accepted", "accepted_to_rag", "rejected"}


def build_quality_report(output_dir: str | Path | None = None) -> dict[str, Any]:
    init_database()
    issues: list[dict[str, Any]] = []
    with get_connection() as conn:
        papers = [dict(row) for row in conn.execute("SELECT * FROM literature_paper").fetchall()]
        chunks = [dict(row) for row in conn.execute("SELECT * FROM literature_chunk").fetchall()]
        artifacts = [dict(row) for row in conn.execute("SELECT * FROM literature_artifact").fetchall()]
        duplicates = [
            dict(row)
            for row in conn.execute(
                """
                SELECT normalized_title, year, count(*) AS count
                FROM literature_paper
                WHERE normalized_title != ''
                GROUP BY normalized_title, year HAVING count(*) > 1
                """
            ).fetchall()
        ]
    for paper in papers:
        if not (paper.get("canonical_title") or "").strip():
            issues.append(_issue("missing_title", "paper", paper["paper_id"]))
        doi = (paper.get("doi") or "").strip()
        if doi and not DOI_RE.match(doi):
            issues.append(_issue("invalid_doi", "paper", paper["paper_id"], doi))
        if paper.get("review_status") not in VALID_REVIEW:
            issues.append(_issue("invalid_review_status", "paper", paper["paper_id"], paper.get("review_status")))
        for field in ("geometry_json", "quality_metrics_json", "defects_json", "measurement_methods_json"):
            try:
                json.loads(paper.get(field) or ("[]" if field.endswith("s_json") else "{}"))
            except json.JSONDecodeError:
                issues.append(_issue("invalid_metadata_json", "paper", paper["paper_id"], field))
    for chunk in chunks:
        if not chunk.get("content"):
            issues.append(_issue("empty_chunk", "chunk", chunk["chunk_id"]))
        if not chunk.get("page_start") or (chunk.get("page_end") or 0) < (chunk.get("page_start") or 0):
            issues.append(_issue("invalid_page_range", "chunk", chunk["chunk_id"]))
        if (chunk.get("token_estimate") or 0) > 700:
            issues.append(_issue("oversized_chunk", "chunk", chunk["chunk_id"], chunk.get("token_estimate")))
        try:
            json.loads(chunk.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            issues.append(_issue("invalid_metadata_json", "chunk", chunk["chunk_id"]))
    for artifact in artifacts:
        if artifact.get("asset_type") == "raw_pdf" and not Path(artifact.get("archived_path") or "").exists():
            issues.append(_issue("missing_archived_pdf", "artifact", artifact["artifact_id"]))
        if artifact.get("parse_status") == "needs_ocr":
            issues.append(_issue("needs_ocr", "artifact", artifact["artifact_id"]))
    for duplicate in duplicates:
        issues.append(_issue("duplicate_paper", "paper_group", f"{duplicate['normalized_title']}|{duplicate['year']}", duplicate["count"]))
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["issue_type"]] = counts.get(issue["issue_type"], 0) + 1
    report = {
        "generated_at": utc_now_iso(),
        "paper_count": len(papers),
        "artifact_count": len(artifacts),
        "chunk_count": len(chunks),
        "issue_count": len(issues),
        "issue_counts": counts,
        "issues": issues,
    }
    target = Path(output_dir) if output_dir else get_project_root() / "data" / "reports"
    target.mkdir(parents=True, exist_ok=True)
    (target / "literature_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Literature Quality Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Papers: {len(papers)}",
        f"- Artifacts: {len(artifacts)}",
        f"- Chunks: {len(chunks)}",
        f"- Issues: {len(issues)}",
        "",
        "## Issue counts",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Audit boundary", "", "Pending literature evidence remains reviewable evidence only; it is not a validated rule, process prior, or BO training sample."])
    (target / "literature_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def _issue(issue_type: str, entity_type: str, entity_id: str, detail: Any = None) -> dict[str, Any]:
    return {"issue_type": issue_type, "entity_type": entity_type, "entity_id": entity_id, "detail": detail}
