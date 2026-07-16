# Tool consolidation matrix

| Removed path | Current disposition |
|---|---|
| task state update tools | `AgentAction.context_updates` + non-blocking `ContextPersistenceService` |
| equipment/profile aliases | `get_equipment_context` |
| RAG/history aliases | `search_knowledge` |
| BO orchestration/iteration aliases | independent `recommend_parameters_bo` |
| RAG parameter aliases | `recommend_parameters_rag` |
| LLM fallback parameter aliases | removed; Main LLM cannot create unsourced numeric candidates |
| multiple Trial services/campaign API | one `manage_trial` Tool backed by `TrialApplicationService` |
| formal Workflow/FSM actions | one `manage_process` Tool inside MainAgentLoop |
| knowledge review/candidate actions | governance sidecar/API; not Agent-facing |
