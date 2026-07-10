# Phase 0 performance baseline

- HEAD: `cb5094903bb83489bb278f34ae7005973cc21ded`
- External LLM/network calls: disabled
- RAG/equipment/database measurements: temporary SQLite backup, not the live database
- Units: milliseconds

| Metric | Status | Samples | P50 | P95 | Scope |
|---|---:|---:|---:|---:|---|
| application_startup | implemented | 5 | 699.084 | 706.241 | Fresh Python process importing ultrafast_memory.app.api; server socket startup excluded. |
| chat_first_event | implemented | 10 | 95.895 | 102.01 | In-process /chat/stream_ndjson generator with MockLLM; HTTP transport excluded. |
| chat_first_token | implemented | 10 | 404.203 | 426.267 | First NDJSON delta event with MockLLM; HTTP transport excluded. |
| chat_total_response | implemented | 10 | 458.897 | 480.664 | Completion of NDJSON stream with MockLLM; HTTP transport excluded. |
| rag_query | implemented | 7 | 732.806 | 1055.633 | Temporary copy of production-size SQLite index; hits=8; evidence_status=sufficient |
| router | implemented | 50 | 24.018 | 26.748 | Rule router including equipment-context read; primary_skill=rag_literature_retrieval |
| equipment_profile_read | implemented | 30 | 23.252 | 27.062 | Active equipment profile and machine-bound construction; active=True |
| database_query | implemented | 100 | 5.836 | 8.239 | SQLite open/read/close COUNT query; rows=8512 |
| bo_agent_adapter | stub | 100 | 0.0 | 0.0 | Not a real recommendation; adapter returns model_status=not_connected. |
| bo_recommendation | implemented | 5 | 120.485 | 136.44 | Real legacy-root recommendation path; model_status=data_driven_bo; candidate_grid_size=500. |
| trial_plan_generation | not_found | 0 | N/A | N/A | No trial planning module/API/service exists at the Phase 0 baseline. |

The `bo_agent_adapter` timing is diagnostic only because the adapter is a stub. The authoritative baseline for a real BO recommendation is `bo_recommendation`, measured through the legacy root project. Trial-plan timing is unavailable because that capability does not exist at this baseline.
