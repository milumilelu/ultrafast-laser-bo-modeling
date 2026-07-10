from __future__ import annotations

from ultrafast_memory.knowledge_review.review_actions import apply_review_action
from ultrafast_memory.knowledge_review.review_queue import get_review_task, list_knowledge_candidates, list_review_tasks
from ultrafast_memory.knowledge_review.schemas import ReviewActionRequest


def list_candidates(status: str = "pending_review") -> list[dict]:
    return list_knowledge_candidates(status)


def list_tasks(status: str = "pending_review") -> list[dict]:
    return list_review_tasks(status)


def get_task(review_id: str) -> dict:
    return get_review_task(review_id)


def apply_action(review_id: str, request: ReviewActionRequest) -> dict:
    return apply_review_action(review_id, request)
