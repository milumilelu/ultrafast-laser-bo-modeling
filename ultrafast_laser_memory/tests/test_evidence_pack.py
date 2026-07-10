from ultrafast_memory.rag.evidence_pack import build_evidence_pack


def test_evidence_pack_requires_traceable_multi_paper_evidence():
    hits = []
    for index, paper_id in enumerate(["p1", "p1", "p2"]):
        hits.append({
            "chunk_id": f"c{index}", "paper_id": paper_id, "content": "TGV evidence", "page_start": 1,
            "page_end": 1, "score": 0.9, "review_status": "pending_review",
            "metadata": {"title": "Study", "material": "glass_wafer", "process_type": "TGV_drilling"},
        })
    pack = build_evidence_pack("TGV", {"material": "glass_wafer", "process_type": "TGV_drilling"}, hits)
    assert pack["evidence_status"] == "sufficient"
    assert pack["hits"][0]["chunk_id"] == "c0"
    assert pack["warnings"]
