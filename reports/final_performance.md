# Final performance

All measurements use MockLLM and a temporary online backup of the live SQLite database.

| Metric | Status | P50 ms | P95 ms | P99 ms | Scope |
|---|---|---:|---:|---:|---|
| application_startup | implemented | 572.152 | 607.429 | 624.404 | Fresh import of split FastAPI app; socket startup excluded. |
| chat_first_event | implemented | 163.952 | 290.048 | 297.147 | In-process NDJSON, MockLLM. |
| chat_first_token | implemented | 163.965 | 290.065 | 297.164 | First delta, MockLLM. |
| chat_total_response | implemented | 163.971 | 290.072 | 297.17 | Complete NDJSON response, MockLLM. |
| rag_query | implemented | 47.031 | 391.39 | 570.578 | Cold cache; chunks=8513; hits=8. |
| rag_query_warm_cache | implemented | 21.191 | 27.206 | 27.359 | Revision-scoped cache; cache_hit=True. |
| router | implemented | 0.006 | 0.006 | 0.011 | Rule router + equipment context; skill=complex_process_task. |
| equipment_profile_read | implemented | 4.194 | 7.476 | 8.933 | active=True |
| database_query | implemented | 3.028 | 4.352 | 10.646 | rows=8513 |
| workflow_event_processing | implemented | 0.013 | 0.015 | 0.016 | Immutable transition; final_sequence=103. |
| bo_dataset_slice | implemented | 0.138 | 0.214 | 0.48 | Strict material/process/equipment/target slice; selected=40. |
| bo_recommendation | implemented | 27.833 | 28.885 | 29.037 | Real GPR application service; status=hybrid_rule_bo; bo_invoked=True. |
| job_enqueue_and_claim | implemented | 70.554 | 76.663 | 86.447 | SQLite transaction path; last_job=job_d1d927ec63ec41afbae708fcee10b010. |
| ocr_per_page | not_measured | None | None | None | No authorized scanned-PDF benchmark corpus or installed PaddleOCR model was supplied; structural OCR job tests are reported separately. |
| trial_plan_generation | implemented | 0.005 | 0.006 | 0.006 | Implemented domain policy; matrix_rows=0. |
| concurrent_5_sessions | implemented | 1196.579 | 1600.794 | 1630.405 | Three batches of five concurrent MockLLM chat sessions. |
| database_growth_20_chats | implemented | None | None | None | Temporary database growth after 20 persisted chat sessions. |
| doctor | implemented | 1069.752 | 1083.184 | 1084.378 | status=healthy; external_call=False. |

Acceptance: **pass** (12/12 checks).
