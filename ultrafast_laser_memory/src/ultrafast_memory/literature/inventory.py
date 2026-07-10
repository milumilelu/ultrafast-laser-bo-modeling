from __future__ import annotations

import hashlib
from pathlib import Path

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.literature.schemas import InventoryRecord


ASSET_NAMES = {
    "paper_table.csv": "structured_paper_table",
    "literature_cards.jsonl": "structured_literature_card",
    "extracted_claims.jsonl": "structured_claims",
    "parameter_table.csv": "structured_parameters",
    "knowledge_candidates.jsonl": "structured_candidates",
    "source_artifacts.json": "source_registry",
    "papers.bib": "bibtex",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify_asset(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "raw_pdf"
    if path.name in ASSET_NAMES:
        return ASSET_NAMES[path.name]
    if path.suffix.lower() == ".json" and path.parent.name == "paper_cards":
        return "structured_literature_card"
    return "unknown"


def related_root(path: Path, scan_root: Path) -> str | None:
    current = path.parent
    while current != scan_root.parent:
        if any((current / name).exists() for name in ASSET_NAMES):
            return str(current.resolve())
        if current == scan_root:
            break
        current = current.parent
    return str(path.parent.resolve()) if path.suffix.lower() == ".pdf" else None


def discover_inventory(root: str | Path, include_unknown: bool = False) -> list[InventoryRecord]:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"literature root does not exist: {root_path}")
    now = utc_now_iso()
    records: list[InventoryRecord] = []
    paths = [root_path] if root_path.is_file() else sorted(p for p in root_path.rglob("*") if p.is_file())
    for path in paths:
        asset_type = classify_asset(path)
        if asset_type == "unknown" and not include_unknown:
            continue
        stat = path.stat()
        sha = sha256_path(path)
        records.append(
            InventoryRecord(
                inventory_id=stable_id("inv", sha, asset_type),
                path=str(path.resolve()),
                asset_type=asset_type,
                sha256=sha,
                file_size_bytes=stat.st_size,
                modified_at=__import__("datetime").datetime.fromtimestamp(
                    stat.st_mtime, tz=__import__("datetime").timezone.utc
                ).isoformat(),
                discovered_at=now,
                related_root=related_root(path, root_path if root_path.is_dir() else root_path.parent),
            )
        )
    return records


def inventory_summary(records: list[InventoryRecord]) -> dict:
    counts: dict[str, int] = {}
    sha_counts: dict[str, int] = {}
    for record in records:
        counts[record.asset_type] = counts.get(record.asset_type, 0) + 1
        sha_counts[record.sha256] = sha_counts.get(record.sha256, 0) + 1
    return {
        "discovered_count": len(records),
        "asset_counts": counts,
        "duplicate_file_count": sum(count - 1 for count in sha_counts.values() if count > 1),
        "unique_sha256_count": len(sha_counts),
    }
