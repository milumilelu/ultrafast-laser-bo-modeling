from ultrafast_memory.literature.chunk_builder import build_chunks
from ultrafast_memory.literature.section_parser import parse_sections
from ultrafast_memory.literature.schemas import PageText


def test_chunk_carries_page_section_and_source():
    pages = [PageText(page_number=1, text="Results\n" + "TGV taper crack result. " * 300)]
    sections = parse_sections("paper1", "artifact1", pages)
    chunks = build_chunks({"paper_id": "paper1", "title": "Study", "review_status": "pending_review"}, sections, min_tokens=10)
    assert chunks
    assert chunks[0].page_start == 1
    assert chunks[0].section_type == "results"
    assert chunks[0].metadata["artifact_id"] == "artifact1"
    assert max(chunk.token_estimate for chunk in chunks) <= 700
