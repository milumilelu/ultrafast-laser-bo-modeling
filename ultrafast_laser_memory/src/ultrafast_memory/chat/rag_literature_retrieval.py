from __future__ import annotations

from typing import Any

from ultrafast_memory.rag.query_service import query_rag


def run_rag_literature_retrieval(
    query: str,
    filters: dict[str, Any] | None = None,
    session_id: str | None = None,
    purpose: str = "literature_background",
    top_k: int = 8,
) -> dict[str, Any]:
    """Execute the internal literature skill and return evidence, citations, and grounded text."""
    evidence = query_rag(
        {
            "query": query,
            "filters": filters or {},
            "session_id": session_id,
            "purpose": purpose,
            "top_k": top_k,
        }
    )
    citations = evidence.get("citations") or []
    if evidence.get("evidence_status") == "insufficient":
        return {"handled": False, "rag_evidence": evidence, "citations": []}
    lines = ["以下结论仅基于已入库、可追溯的文献 chunk；pending_review 内容属于候选证据：", ""]
    for hit, citation in zip(evidence.get("hits", [])[:5], citations[:5]):
        excerpt = " ".join((hit.get("content") or "").split())[:360]
        lines.append(f"- {excerpt} {citation.get('internal')}")
    lines.extend(["", f"证据状态：{evidence.get('evidence_status')}。"])
    if evidence.get("evidence_status") != "sufficient":
        lines.append("现有证据不足以支持确定性工艺参数结论。")
    return {
        "handled": True,
        "assistant_message": "\n".join(lines),
        "rag_evidence": evidence,
        "citations": citations,
    }
