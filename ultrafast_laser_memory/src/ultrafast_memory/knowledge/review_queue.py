from __future__ import annotations

from ultrafast_memory.db.session import get_connection


def list_candidates(status: str = "candidate") -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM experience_candidate WHERE status = ? ORDER BY extracted_at DESC",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]


def _review(candidate_id: str, status: str, comment: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE experience_candidate SET status = ?, review_comment = ? WHERE candidate_id = ?",
            (status, comment, candidate_id),
        )
        conn.commit()


def accept_candidate(candidate_id: str, comment: str = "") -> None:
    _review(candidate_id, "accepted", comment)


def reject_candidate(candidate_id: str, comment: str = "") -> None:
    _review(candidate_id, "rejected", comment)


def mark_needs_more_evidence(candidate_id: str, comment: str = "") -> None:
    _review(candidate_id, "needs_more_evidence", comment)
