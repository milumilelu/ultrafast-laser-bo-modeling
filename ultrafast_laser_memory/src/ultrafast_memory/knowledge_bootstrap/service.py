from __future__ import annotations

from ultrafast_memory.knowledge_bootstrap.candidate_builder import build_knowledge_candidate
from ultrafast_memory.knowledge_bootstrap.claim_extractor import extract_claims_from_source
from ultrafast_memory.knowledge_bootstrap.evidence_gap_detector import detect_evidence_gap
from ultrafast_memory.knowledge_bootstrap.query_generator import generate_search_queries
from ultrafast_memory.knowledge_bootstrap.schemas import BootstrapWebRequest, BootstrapWebResponse, EvidenceGapRequest, EvidenceGapResponse
from ultrafast_memory.knowledge_bootstrap.source_registry import register_external_source
from ultrafast_memory.knowledge_bootstrap.web_search_client import BaseWebSearchClient, MockWebSearchClient
from ultrafast_memory.knowledge_review.review_queue import create_review_task


def check_evidence_gap(request: EvidenceGapRequest) -> EvidenceGapResponse:
    result = detect_evidence_gap(request.question, request.task_spec, request.internal_hits)
    return EvidenceGapResponse.model_validate(result)


def bootstrap_from_web(
    request: BootstrapWebRequest,
    web_search_client: BaseWebSearchClient | None = None,
) -> BootstrapWebResponse:
    queries = generate_search_queries(request.task_spec, request.question, request.query_intent)
    client = web_search_client or MockWebSearchClient()
    raw_sources = client.search(queries, max_sources=request.max_sources)
    sources = []
    candidates = []
    review_tasks = []

    for raw_source in raw_sources:
        source = register_external_source(raw_source)
        sources.append(source)
        for claim in extract_claims_from_source(source, request.task_spec):
            candidate = build_knowledge_candidate(source, claim)
            candidates.append(candidate)
            if request.review_required:
                review_tasks.append(
                    create_review_task(
                        candidate["candidate_id"],
                        candidate.get("risk_level") or "medium",
                        candidate.get("suggested_action") or "needs_more_evidence",
                    )
                )

    return BootstrapWebResponse(
        sources=sources,
        knowledge_candidates=candidates,
        review_tasks=review_tasks,
        auto_indexed=[],
        requires_review=candidates,
    )


def bootstrap_external_knowledge(
    task_spec: dict,
    question: str | None = None,
    query_intent: str = "find_literature_prior",
    max_sources: int = 5,
) -> dict:
    response = bootstrap_from_web(
        BootstrapWebRequest(
            task_spec=task_spec,
            question=question,
            query_intent=query_intent,
            max_sources=max_sources,
            review_required=True,
        )
    )
    candidate_ids = [item["candidate_id"] for item in response.knowledge_candidates]
    review_task_ids = [item["review_id"] for item in response.review_tasks]
    return {
        "executed": True,
        "sources": response.sources,
        "created_candidates": len(candidate_ids),
        "created_review_tasks": len(review_task_ids),
        "candidate_ids": candidate_ids,
        "review_task_ids": review_task_ids,
        "next_action": "expert_review_required",
        "response": response.model_dump(mode="json"),
    }
