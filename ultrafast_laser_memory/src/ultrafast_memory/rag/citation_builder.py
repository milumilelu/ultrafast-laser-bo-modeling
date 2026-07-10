from __future__ import annotations

from typing import Any


def build_citation(hit: dict[str, Any]) -> dict[str, Any]:
    page_start = hit.get("page_start")
    page_end = hit.get("page_end")
    page = f"p.{page_start}" if page_start == page_end else f"pp.{page_start}-{page_end}"
    author_year = ", ".join(item for item in [hit.get("authors") or "Unknown author", str(hit.get("year") or "n.d.")] if item)
    doi = hit.get("doi") or ""
    return {
        "paper_id": hit.get("paper_id"),
        "chunk_id": hit.get("chunk_id"),
        "page_start": page_start,
        "page_end": page_end,
        "doi": doi,
        "internal": f"[{hit.get('paper_id')}, {page}, {hit.get('chunk_id')}]",
        "source_reference": f"{author_year}, {page}" + (f", DOI {doi}" if doi else ""),
    }


def build_citations(evidence_pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [build_citation(hit) for hit in evidence_pack.get("hits", [])]
