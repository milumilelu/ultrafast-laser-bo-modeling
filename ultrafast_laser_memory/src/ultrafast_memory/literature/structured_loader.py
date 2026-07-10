from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from ultrafast_memory.literature.schemas import LiteratureCard


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"expected object at {path}:{number}")
        rows.append(value)
    return rows


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _card_sources(root: Path) -> list[Path]:
    primary = root / "literature_cards.jsonl"
    if primary.exists():
        return [primary]
    paper_cards = sorted((root / "paper_cards").glob("*.json")) if (root / "paper_cards").exists() else []
    if paper_cards:
        return paper_cards
    table = root / "paper_table.csv"
    return [table] if table.exists() else []


def _iter_cards(path: Path) -> Iterable[dict[str, Any]]:
    if path.name == "literature_cards.jsonl":
        yield from _read_jsonl(path)
    elif path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            yield value
    elif path.suffix.lower() == ".csv":
        yield from _read_csv(path)


def load_structured_deliverables(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve()
    cards: list[LiteratureCard] = []
    errors: list[str] = []
    for source in _card_sources(path):
        for index, raw in enumerate(_iter_cards(source), 1):
            try:
                cards.append(LiteratureCard.model_validate(raw))
            except ValidationError as exc:
                errors.append(f"{source}:{index}: {exc}")
    claims_path = path / "extracted_claims.jsonl"
    candidates_path = path / "knowledge_candidates.jsonl"
    params_path = path / "parameter_table.csv"
    registry_path = path / "source_artifacts.json"
    claims = _read_jsonl(claims_path) if claims_path.exists() else []
    candidates = _read_jsonl(candidates_path) if candidates_path.exists() else []
    parameters = _read_csv(params_path) if params_path.exists() else []
    source_registry: dict[str, Any] = {}
    if registry_path.exists():
        value = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            source_registry = value
    return {
        "root": str(path),
        "cards": cards,
        "claims": claims,
        "candidates": candidates,
        "parameters": parameters,
        "source_registry": source_registry,
        "errors": errors,
    }
