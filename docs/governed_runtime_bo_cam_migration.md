# Governed Runtime, BO, CAM, and Document Pipeline

## Implemented boundaries

- `ultrafast_agent`: immutable workflow context/events, tool execution, persistent jobs, evolution, document-ingestion, and process-recommendation application services.
- `ultrafast_domain`: pure process-recommendation, document, and evolution models.
- `ultrafast_bo`: the formal `BORecommendationService`, strict dataset slicing, eligibility, readiness, model lifecycle, and constrained search-space compilation.
- `ultrafast_integrations`: SQLite repositories, Generic/ConfigDriven CAM adapters, PaddleOCR adapter, and the disabled multimodal vision adapter.
- `ultrafast_memory`: transport and compatibility entrypoints. New document and recommendation modules only re-export application services; compatibility adapters map fields only.

The normal and NDJSON chat endpoints execute the same non-streaming workflow. NDJSON is a renderer over the resulting public workflow events and response; it does not run a second business path.

## Governance order

1. Use task-scoped, eligible BO data when readiness permits.
2. Use approved process priors or validated rules.
3. Use RAG evidence only as a reviewed candidate source.
4. Use an LLM candidate only for a reviewable trial-cut proposal.

OCR and vision outputs are candidate-only. No code path writes them directly to a BO sample, process prior, validated rule, process recommendation, or CAM export.

## Database migrations

- `0007_runtime_jobs_evolution`: background jobs/events and immutable evolution records.
- `0008_bo_governance_lifecycle`: BO candidates, approvals, dataset/model versions, evaluations, and replay traces.
- `0009_process_recommendation_cam_documents`: recommendation chains, CAM exports, raw feedback, and OCR elements/candidates.

Primary audit records are append-only; mutable status fields change only through governed state transitions. Existing tables and columns are unchanged, so old readers continue to work. Evolution has both an in-memory test repository and a SQLite repository verified across service instances.

### Forward strategy

Run any normal CLI/API command or `python -m ultrafast_memory.app.cli init-db`; startup applies missing migrations transactionally. Before production migration, back up the SQLite database and compare table row counts.

### Rollback strategy

Application rollback is compatible with the added tables: deploy the previous code and leave new tables in place. Do not drop append-only history. If physical rollback is mandatory, restore the pre-migration SQLite backup; this discards records written after the backup and therefore requires an explicit data-retention decision.

## CAM contract

`GET /api/v1/process-recommendations/{id}/cam-parameters` returns Generic CAM JSON schema `1.0`. Export requires `ready_for_cam`, a complete recipe, units, and parameter metadata. Adapters only map names, units, enumerations, required fields, and serialization. They cannot run BO, widen constraints, fill critical values, connect to equipment, or emit control commands.

The vendor input template is still unfilled. Consequently no real-vendor adapter or golden vendor fixture is claimed. `ConfigDrivenCamAdapter` profiles are mapping configurations, not evidence of vendor compatibility.

## OCR and vision

- Native-text PDFs skip OCR.
- Scanned PDFs/images enqueue `paddleocr_document` with idempotency key `document_hash:parser_version`.
- PaddleOCR is a lazy optional dependency; an unavailable installation returns `provider_unavailable`.
- Vision semantic analysis is implemented as an adapter skeleton, disabled by default, and absent from Chat, TUI, route, and public API registries.

## Known limitations

- No vendor CAM mapping can be completed until Gate D inputs are supplied.
- PaddleOCR accuracy is not evaluated and the model is not trained here.
- Vision accuracy is not evaluated and its output remains `experimental_unvalidated`.
- No authentication/RBAC, device connection/control, CAD/CAM geometry, toolpath generation, multi-objective Pareto delivery, or cross-material transfer learning is implemented.
- The lightweight constrained BO baseline uses deterministic CPU candidate generation and a Matern 5/2 ARD GP. BoTorch qLogNEI remains an optional future backend; the recorded acquisition version makes this explicit.
