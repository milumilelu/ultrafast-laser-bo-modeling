from __future__ import annotations

import json
from typing import Any

from ultrafast_memory.rag.metadata_filter import metadata_for_hit
from ultrafast_memory.rag.schemas import EvidenceHit, EvidencePack


def build_evidence_pack(query: str, filters: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_hits: list[EvidenceHit] = []
    warnings: list[str] = []
    for hit in hits:
        metadata = metadata_for_hit(hit)
        usable = _as_list(metadata.get("usable_for"))
        not_usable = _as_list(metadata.get("not_usable_for"))
        review_status = hit.get("review_status") or metadata.get("review_status") or "pending_review"
        if review_status == "pending_review" and "pending_review evidence is candidate evidence" not in warnings:
            warnings.append("pending_review evidence is candidate evidence")
        evidence_hits.append(
            EvidenceHit(
                chunk_id=hit["chunk_id"],
                paper_id=hit["paper_id"],
                title=metadata.get("title") or hit.get("canonical_title") or hit.get("title") or "",
                authors=metadata.get("authors") or hit.get("authors") or "",
                year=str(metadata.get("year") or hit.get("year") or ""),
                doi=metadata.get("doi") or hit.get("doi") or "",
                page_start=int(hit.get("page_start") or metadata.get("page_start") or 1),
                page_end=int(hit.get("page_end") or metadata.get("page_end") or hit.get("page_start") or 1),
                section_type=hit.get("section_type") or metadata.get("section_type") or "unknown",
                content=hit.get("content") or "",
                score=float(hit.get("score") or 0.0),
                scenario_id=metadata.get("scenario_id") or "",
                material=metadata.get("material") or "",
                process_type=metadata.get("process_type") or "",
                evidence_level=hit.get("evidence_level") or metadata.get("evidence_level") or "",
                review_status=review_status,
                usable_for=usable,
                not_usable_for=not_usable,
            )
        )
    paper_count = len({hit.paper_id for hit in evidence_hits})
    matched_condition = any(
        (not filters.get("material") or hit.material == filters.get("material"))
        and (not filters.get("process_type") or hit.process_type == filters.get("process_type"))
        for hit in evidence_hits
    )
    if len(evidence_hits) >= 3 and paper_count >= 2 and matched_condition:
        status = "sufficient"
        missing = []
    elif evidence_hits:
        status = "partial"
        missing = ["at least three relevant chunks from two papers with matching material/process"]
    else:
        status = "insufficient"
        missing = ["matching traceable literature chunks"]
    return EvidencePack(
        query=query,
        filters=filters,
        evidence_status=status,
        hits=evidence_hits,
        missing_evidence=missing,
        warnings=warnings,
    ).model_dump(mode="json")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [str(item) for item in parsed] if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            return [value] if value else []
    return []
