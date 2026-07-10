from __future__ import annotations

from typing import Any

from ultrafast_memory.rag.metadata_filter import enforce_purpose, metadata_for_hit


PREFERRED_SECTIONS = {"results", "discussion", "conclusion"}


def rerank_hits(
    hits: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    purpose: str = "literature_background",
    top_k: int = 8,
) -> list[dict[str, Any]]:
    filters = filters or {}
    output = []
    for hit in hits:
        if hit.get("review_status") == "rejected" or not enforce_purpose(hit, purpose):
            continue
        metadata = metadata_for_hit(hit)
        score = float(hit.get("score") or 0.0)
        for key, bonus in (("material", 0.12), ("process_type", 0.1), ("component_type", 0.08)):
            if filters.get(key) and (metadata.get(key) or hit.get(key)) == filters[key]:
                score += bonus
        if (hit.get("section_type") or metadata.get("section_type")) in PREFERRED_SECTIONS:
            score += 0.07
        if metadata.get("doi"):
            score += 0.03
        if hit.get("page_start") and hit.get("page_end"):
            score += 0.02
        if purpose in (metadata.get("not_usable_for") or []):
            score -= 0.5
        output.append({**hit, "score": score})
    return sorted(output, key=lambda row: row["score"], reverse=True)[:top_k]
