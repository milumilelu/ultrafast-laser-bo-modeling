from __future__ import annotations

LEVEL_0_UNVERIFIED_CANDIDATE = "LEVEL_0_UNVERIFIED_CANDIDATE"
LEVEL_1_RAG_BACKGROUND = "LEVEL_1_RAG_BACKGROUND"
LEVEL_2_LITERATURE_EVIDENCE = "LEVEL_2_LITERATURE_EVIDENCE"
LEVEL_3_PROCESS_PRIOR = "LEVEL_3_PROCESS_PRIOR"
LEVEL_4_VALIDATED_RULE = "LEVEL_4_VALIDATED_RULE"
LEVEL_5_BO_TRAINING_SAMPLE = "LEVEL_5_BO_TRAINING_SAMPLE"

IMPLEMENTED_ACTIONS = {
    "reject",
    "needs_more_evidence",
    "accept_to_rag",
    "accept_as_literature_evidence",
    "withdraw",
}

STUB_ACTIONS = {
    "accept_as_process_prior",
    "promote_to_validated_rule",
    "approve_for_bo_training",
}
