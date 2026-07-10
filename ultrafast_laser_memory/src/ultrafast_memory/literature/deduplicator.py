from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.literature.canonicalizer import normalize_doi, normalize_title


def find_canonical_paper(conn, metadata: dict[str, Any], artifact_id: str | None = None) -> dict[str, Any]:
    if artifact_id:
        row = conn.execute(
            """
            SELECT p.* FROM literature_paper p
            JOIN literature_paper_source s ON s.paper_id = p.paper_id
            WHERE s.artifact_id = ? LIMIT 1
            """,
            (artifact_id,),
        ).fetchone()
        if row:
            return {"paper": dict(row), "match_type": "artifact", "needs_review": False}
    doi = normalize_doi(str(metadata.get("doi") or ""))
    if doi:
        row = conn.execute("SELECT * FROM literature_paper WHERE lower(doi) = ? LIMIT 1", (doi,)).fetchone()
        if row:
            return {"paper": dict(row), "match_type": "doi", "needs_review": False}
    title = normalize_title(str(metadata.get("title") or metadata.get("canonical_title") or ""))
    year = str(metadata.get("year") or "")
    if title:
        row = conn.execute(
            "SELECT * FROM literature_paper WHERE normalized_title = ? AND coalesce(year, '') = ? LIMIT 1",
            (title, year),
        ).fetchone()
        if row:
            return {"paper": dict(row), "match_type": "title_year", "needs_review": False}
        candidates = conn.execute(
            "SELECT * FROM literature_paper WHERE coalesce(year, '') IN (?, ?, ?)",
            (year, str(int(year) - 1) if year.isdigit() else "", str(int(year) + 1) if year.isdigit() else ""),
        ).fetchall()
        first_author = _first_author(str(metadata.get("authors") or ""))
        for candidate in candidates:
            candidate_dict = dict(candidate)
            ratio = SequenceMatcher(None, title, candidate_dict.get("normalized_title") or "").ratio()
            if ratio >= 0.9 and first_author and first_author == _first_author(candidate_dict.get("authors") or ""):
                return {"paper": candidate_dict, "match_type": "fuzzy_needs_review", "needs_review": True}
    return {"paper": None, "match_type": "new", "needs_review": False}


def canonical_paper_id(metadata: dict[str, Any]) -> str:
    doi = normalize_doi(str(metadata.get("doi") or ""))
    title = normalize_title(str(metadata.get("title") or metadata.get("canonical_title") or ""))
    year = str(metadata.get("year") or "")
    preferred = str(metadata.get("paper_id") or "").strip()
    return preferred or stable_id("paper", doi or title, year)


def _first_author(authors: str) -> str:
    first = authors.split(";")[0].split(",")[0].strip().lower()
    return " ".join(first.split())
