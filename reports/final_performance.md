# Final performance

All measurements use MockLLM and a temporary online backup of the live SQLite database.

| Metric | Status | P50 ms | P95 ms | P99 ms | Scope |
|---|---|---:|---:|---:|---|
| application_startup | implemented | 599.409 | 729.359 | 743.007 | Fresh import of split FastAPI app; socket startup excluded. |
| chat_first_event | implemented | 31.389 | 59.542 | 62.724 | In-process NDJSON, MockLLM. |
| chat_first_token | implemented | 141.348 | 302.376 | 308.825 | First delta, MockLLM. |
| chat_total_response | implemented | 168.83 | 333.851 | 354.096 | Complete NDJSON response, MockLLM. |
| rag_query | implemented | 53.97 | 556.343 | 811.255 | Cold cache; chunks=8513; hits=8. |
| rag_query_warm_cache | implemented | 19.688 | 24.881 | 25.286 | Revision-scoped cache; cache_hit=True. |
| router | implemented | 4.647 | 9.149 | 9.544 | Rule router + equipment context; skill=rag_literature_retrieval. |
| equipment_profile_read | implemented | 4.087 | 6.547 | 7.57 | active=True |
| database_query | implemented | 3.066 | 5.335 | 6.232 | rows=8513 |
| bo_recommendation | implemented | 45.241 | 58.389 | 61.224 | Real GPR application service; status=hybrid_rule_bo; bo_invoked=True. |
| trial_plan_generation | implemented | 0.013 | 0.05 | 0.066 | Implemented domain policy; matrix_rows=5. |
| concurrent_5_sessions | implemented | 983.822 | 1197.657 | 1245.04 | Three batches of five concurrent MockLLM chat sessions. |
| database_growth_20_chats | implemented | None | None | None | Temporary database growth after 20 persisted chat sessions. |
| doctor | implemented | 1491.515 | 1553.069 | 1558.54 | status=healthy; external_call=False. |

Acceptance: **pass** (12/12 checks).
