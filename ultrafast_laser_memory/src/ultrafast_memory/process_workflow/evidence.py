from __future__ import annotations

from typing import Any


def credibility_summary(hits: list[dict[str, Any]], task: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        review = hit.get("review_status") or metadata.get("review_status") or "pending_review"
        matches = {
            "material_match": _match(task.get("material"), metadata.get("material")),
            "thickness_match": _match(task.get("thickness_mm"), metadata.get("thickness_mm")),
            "process_match": _match(task.get("process_type"), metadata.get("process_type")),
            "equipment_match": bool(metadata.get("equipment_match", False)),
        }
        traceable = bool(hit.get("paper_id") and hit.get("chunk_id") and hit.get("page_start") is not None)
        score = sum(matches.values()) + int(traceable) + int(bool(metadata.get("doi"))) + int(review == "approved")
        credibility = "high" if score >= 6 else "medium" if score >= 3 else "low"
        sources.append({
            "paper_id": hit.get("paper_id", ""), "title": metadata.get("title", ""),
            "authors": metadata.get("authors", ""), "year": metadata.get("year", ""),
            "doi": metadata.get("doi", ""), "page_start": hit.get("page_start"),
            "page_end": hit.get("page_end"), "chunk_id": hit.get("chunk_id", ""),
            "review_status": review, "evidence_level": hit.get("evidence_level", "raw_literature"),
            "relevance_score": hit.get("score", 0), "applicability": matches,
            "credibility": credibility, "limitations": _limitations(traceable, matches, review),
        })
    approved = sum(s["review_status"] == "approved" for s in sources)
    rejected = sum(s["review_status"] == "rejected" for s in sources)
    pending = len(sources) - approved - rejected
    high_independent = len({s["paper_id"] for s in sources if s["credibility"] == "high" and s["review_status"] == "approved"})
    status = "sufficient" if high_independent >= 2 else "partial" if sources else "insufficient"
    return {"evidence_status": status, "sources": sources, "approved_source_count": approved,
            "pending_source_count": pending, "rejected_source_count": rejected,
            "warnings": [] if status == "sufficient" else ["not authorized for direct formal parameter recommendation"]}


def _match(expected: Any, actual: Any) -> bool:
    return expected is not None and actual is not None and str(expected).lower() == str(actual).lower()


def _limitations(traceable: bool, matches: dict[str, bool], review: str) -> list[str]:
    result = []
    if not traceable:
        result.append("source/page traceability incomplete")
    if review != "approved":
        result.append("knowledge review incomplete")
    result.extend(f"{key} false" for key, value in matches.items() if not value)
    return result
