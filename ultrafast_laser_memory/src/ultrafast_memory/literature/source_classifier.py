from __future__ import annotations

from pathlib import Path


def classify_source_root(root: str | Path) -> dict:
    path = Path(root).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    has_raw = any(path.rglob("*.pdf"))
    has_cards = any(path.rglob("literature_cards.jsonl")) or any(path.rglob("paper_cards/*.json"))
    has_table = any(path.rglob("paper_table.csv"))
    has_claims = any(path.rglob("extracted_claims.jsonl"))
    has_parameters = any(path.rglob("parameter_table.csv"))
    if (has_cards or has_table) and has_raw:
        mode = "structured_first_with_pdf_backfill"
    elif has_cards or has_table:
        mode = "structured_only"
    elif has_raw:
        mode = "raw_pdf_only"
    else:
        mode = "mixed_unresolved"
    return {
        "root": str(path),
        "has_raw_pdfs": has_raw,
        "has_literature_cards": has_cards,
        "has_paper_table": has_table,
        "has_claims": has_claims,
        "has_parameters": has_parameters,
        "recommended_mode": mode,
    }


def discover_structured_roots(root: str | Path) -> list[Path]:
    path = Path(root).expanduser().resolve()
    roots = {
        item.parent
        for pattern in ("literature_cards.jsonl", "paper_table.csv")
        for item in path.rglob(pattern)
    }
    return sorted(roots)
