from ultrafast_memory.literature.inventory import discover_inventory
from ultrafast_memory.literature.source_classifier import classify_source_root


def test_inventory_detects_mixed_assets(mixed_literature_root):
    records = discover_inventory(mixed_literature_root)
    types = {record.asset_type for record in records}
    assert {"raw_pdf", "structured_literature_card", "structured_paper_table", "structured_candidates"} <= types
    assert classify_source_root(mixed_literature_root)["recommended_mode"] == "structured_first_with_pdf_backfill"
