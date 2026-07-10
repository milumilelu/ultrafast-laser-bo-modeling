from enum import StrEnum


class KnowledgeUse(StrEnum):
    BACKGROUND_EXPLANATION = "background_explanation"
    PARAMETER_RECOMMENDATION = "parameter_recommendation"
    BO_SEARCH_BOUND = "bo_search_bound"
    CANDIDATE_FILTER = "candidate_filter"
    SAFETY_THRESHOLD = "safety_threshold"
